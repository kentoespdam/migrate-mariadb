import threading
import time
from datetime import timedelta
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ProgressBar, RichLog

from ...db.connection import get_connection, get_streaming_connection
from ...db.engine import BatchResult, MigrationResult, WriteMode, migrate_table
from ...db.metadata import TableInfo

# THREAD CONTRACT:
#  - run_migration() & handle_batch_done() berjalan di worker thread.
#  - Mutasi atribut self.* (rows_completed, tables_completed) HANYA di
#    main thread → akses lewat self.app.call_from_thread(method, ...).


class MigrationScreen(Screen):
    """Screen for monitoring migration progress."""

    def __init__(
        self,
        selected_tables: list[TableInfo],
        mappings: dict[str, dict],
        mode: str,
        dry_run: bool,
        batch_size: int,
    ):
        super().__init__()
        self.selected_tables = selected_tables
        self.mappings = mappings
        self.write_mode = WriteMode(mode)
        self.dry_run = dry_run
        self.batch_size = batch_size

        self.start_time = 0
        self.total_rows = sum(t.row_count for t in selected_tables)
        self.rows_completed = 0
        self.rows_completed_in_table = 0
        self.tables_completed = 0

        # Implementation of AD-2: Cooperative cancellation & pause
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Set = running, Clear = paused

        # Widget cache (AD-3)
        self._pb_overall = None
        self._pb_current = None
        self._lbl_speed = None
        self._lbl_elapsed = None
        self._lbl_eta = None
        self._lbl_current_table = None
        self._log_widget = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="progress-section"):
            yield Label("Overall Progress", classes="progress-label")
            yield ProgressBar(
                total=len(self.selected_tables), show_eta=False, id="overall-progress"
            )

            yield Label(
                "Current Table Progress", id="current-table-label", classes="progress-label"
            )
            yield ProgressBar(total=100, show_eta=True, id="current-progress")

            with Horizontal(id="stats-row"):
                yield Label("Speed: 0 rows/s", id="speed-label")
                yield Label("Elapsed: 00:00", id="elapsed-label")
                yield Label("ETA: --:--", id="eta-label")

        yield Label("Migration Log", classes="log-header")
        yield RichLog(id="migration-log", highlight=True, markup=True)

        with Horizontal(classes="button-row"):
            yield Button("Cancel", variant="error", id="cancel-btn")
            yield Button("Pause", id="pause-btn")
            yield Button("Done", variant="success", id="done-btn", disabled=True)

        yield Footer()

    def on_mount(self) -> None:
        # Cache widget references
        self._pb_overall = self.query_one("#overall-progress", ProgressBar)
        self._pb_current = self.query_one("#current-progress", ProgressBar)
        self._lbl_speed = self.query_one("#speed-label", Label)
        self._lbl_elapsed = self.query_one("#elapsed-label", Label)
        self._lbl_eta = self.query_one("#eta-label", Label)
        self._lbl_current_table = self.query_one("#current-table-label", Label)
        self._log_widget = self.query_one("#migration-log", RichLog)

        self.log_info(f"Starting migration for {len(self.selected_tables)} tables...")
        if self.dry_run:
            self.log_info("[yellow]DRY RUN MODE ENABLED - No writes to target[/]")

        self.start_time = time.time()
        self.run_migration()

    def log_info(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self._log_widget.write(f"[{timestamp}] {message}")

    @work(thread=True)
    def run_migration(self) -> None:
        results = []
        try:
            # Source connection must be streaming (use_pure=True for SSCursor)
            with (
                get_streaming_connection(self.app.source_config) as src_conn,
                get_connection(self.app.target_config) as tgt_conn
            ):
                from ...db.engine import count_rows

                for i, table in enumerate(self.selected_tables):
                    if self.cancel_event.is_set():
                        break

                    # Bug #1: Get exact count for progress bar
                    try:
                        exact = count_rows(src_conn, table.name)
                    except Exception:
                        exact = None

                    self.app.call_from_thread(self.prepare_table, table, exact, i)

                    # Get column mapping
                    table_mapping = self.mappings.get(table.name)
                    if not table_mapping:
                        # Default mapping: identity for all source columns
                        from ...db.metadata import get_columns

                        cols_a_info = get_columns(
                            src_conn, self.app.source_config.database, table.name
                        )
                        cols_a = [c.name for c in cols_a_info]
                        table_mapping = {c: c for c in cols_a}
                    else:
                        cols_a = list(table_mapping.keys())

                    # Implementation of AD-1: propagate src_conn directly
                    res = migrate_table(
                        src_conn=src_conn,
                        tgt_conn=tgt_conn,
                        table=table.name,
                        columns_a=cols_a,
                        column_map=table_mapping,
                        mode=self.write_mode,
                        batch_size=self.batch_size,
                        dry_run=self.dry_run,
                        on_batch_done=lambda b: self.app.call_from_thread(
                            self._update_ui_batch, b
                        ),
                        cancel_event=self.cancel_event,
                        pause_event=self.pause_event,
                    )
                    results.append(res)
                    self.app.call_from_thread(self.finish_table, res)

                    if res.cancelled:
                        self.app.call_from_thread(self.log_info, "[red]Migration cancelled.[/]")
                        break

            self.app.call_from_thread(self.all_done, results)

        except Exception as e:
            import logging

            from ...logging_setup import log_exception

            log_exception(
                logging.getLogger("pysync_maria.migration"),
                "run_migration crashed",
                e,
                screen="MigrationScreen",
                tables=[t.name for t in self.selected_tables],
                completed=self.tables_completed,
            )
            self.app.call_from_thread(self.log_info, f"[bold red]Critical Error: {e}[/]")

    def prepare_table(self, table: TableInfo, exact_rows: int | None, index: int) -> None:
        self.rows_completed_in_table = 0
        self._lbl_current_table.update(f"Current Table: [bold]{table.name}[/]")
        self._pb_current.update(total=exact_rows, progress=0)

        # Log with best available count
        display_count = exact_rows if exact_rows is not None else table.row_count
        self.log_info(f"▶️ Processing [cyan]{table.name}[/] ({display_count:,} rows)...")

    def _update_ui_batch(self, batch: BatchResult) -> None:
        try:
            self.rows_completed += batch.rows_read
            self.rows_completed_in_table += batch.rows_read

            if self._pb_current.total is None:
                # Textual PB: If total is None, setting progress makes it indeterminate pulse
                # but we want to show raw numbers in label
                self._pb_current.update(progress=self.rows_completed_in_table)
            else:
                self._pb_current.advance(batch.rows_read)

            elapsed = time.time() - self.start_time
            speed = self.rows_completed / elapsed if elapsed > 0 else 0

            self._lbl_speed.update(f"Speed: {format(int(speed), ',')} rows/s")
            self._lbl_elapsed.update(f"Elapsed: {timedelta(seconds=int(elapsed))!s}")

            remaining_rows = max(0, self.total_rows - self.rows_completed)
            eta = remaining_rows / speed if speed > 0 else 0
            self._lbl_eta.update(f"ETA: {timedelta(seconds=int(eta))!s}")
        except Exception as e:
            import logging

            from ...logging_setup import log_exception

            log_exception(
                logging.getLogger("pysync_maria.tui.migration"),
                "UI batch update failed",
                e,
                batch=batch.batch_number,
                table=batch.table_name,
            )

    def finish_table(self, res: MigrationResult) -> None:
        self.tables_completed += 1
        self._pb_overall.advance(1)

        # Force current progress bar to 100% (or actual read count)
        # to close the gap if estimate was off
        self._pb_current.update(total=res.total_rows_read, progress=res.total_rows_read)

        if res.cancelled:
            status_icon = "🛑"
            msg = "cancelled"
        else:
            status_icon = (
                "✅" if res.status == "success" else "⚠️" if res.status == "partial" else "❌"
            )
            msg = f"finished: {res.total_rows_written:,} rows"

        self.log_info(
            f"{status_icon} [bold]{res.table_name}[/] {msg} in {res.elapsed_seconds:.1f}s"
        )

        if res.warnings:
            for warn in res.warnings:
                self.log_info(f"   [yellow]Warning: {warn}[/]")
        if res.errors:
            for err in res.errors[:5]:  # Log first 5 errors
                self.log_info(f"   [red]Error: {err}[/]")

    def all_done(self, results: list[MigrationResult]) -> None:
        self.log_info("[bold green]Migration process completed![/]")
        self.query_one("#done-btn").disabled = False
        self.query_one("#cancel-btn").disabled = True
        self.query_one("#pause-btn").disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.cancel_event.set()
            # Also cancel the textual worker if any
            self.workers.cancel_all()
            self.notify("Cancelling migration...", severity="warning")
            event.button.disabled = True
            self.query_one("#pause-btn").disabled = True
        elif event.button.id == "pause-btn":
            self.action_toggle_pause()
        elif event.button.id == "done-btn":
            self.app.pop_screen()

    def action_export_log(self) -> None:
        """Export the current RichLog to a file (Fix for D3)."""
        export_dir = Path.home() / ".pysync-maria" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"migration_{int(time.time())}.log"
        file_path = export_dir / filename

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"Migration Log - {time.ctime()}\n")
                f.write("=" * 40 + "\n")
                # Iterate through lines and strip rich markup
                for line in self._log_widget.lines:
                    # In Textual, RichLog.lines is a list of Strip objects
                    f.write(line.text + "\n")

            self.notify(f"Log exported to {file_path}")
        except Exception as e:
            import logging

            from ...logging_setup import log_exception

            log_exception(
                logging.getLogger("pysync_maria.tui.migration"),
                "Failed to export log",
                e,
                file_path=str(file_path),
            )
            self.notify(f"Failed to export log: {e}", severity="error")

    BINDINGS = (
        ("e", "export_log", "Export Log"),
        ("p", "toggle_pause", "Pause/Resume"),
    )

    def action_toggle_pause(self) -> None:
        """Implementation of D4: Pause/Resume using threading.Event."""
        btn = self.query_one("#pause-btn", Button)
        if self.pause_event.is_set():
            self.pause_event.clear()
            btn.label = "Resume"
            self.notify("Migration paused", severity="information")
            self.log_info("[yellow]Migration paused by user.[/]")
        else:
            self.pause_event.set()
            btn.label = "Pause"
            self.notify("Migration resumed", severity="information")
            self.log_info("[green]Migration resumed.[/]")
