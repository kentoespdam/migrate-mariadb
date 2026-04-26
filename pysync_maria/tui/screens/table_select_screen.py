from textual import work
from textual.worker import get_current_worker
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

from ...db.connection import get_connection
from ...db.metadata import TableInfo, format_size, get_columns, get_tables
from ..modals.confirm_modal import ConfirmModal
from ..modals.mapping_modal import MappingModal
from .migration_screen import MigrationScreen


class TableSelectScreen(Screen):
    """Screen for selecting tables to migrate."""

    def __init__(self):
        super().__init__()
        self.tables_data: list[TableInfo] = []
        self.selected_tables = set()
        self.schema_status: dict[str, str] = {}
        self.table_mappings = {} # table_name -> dict[source_col, target_col | None]
        self.write_mode = "REPLACE"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Database Overview & Table Selection", id="connection-title")

        yield Input(placeholder="Search tables (Case-insensitive)...", id="table-filter")
        yield DataTable(id="table-list")

        with Horizontal(id="table-footer"):
            yield Label("Write Mode:", classes="footer-label")
            yield Select(
                [("REPLACE INTO", "REPLACE"), ("ON DUPLICATE KEY UPDATE", "UPDATE"), ("INSERT IGNORE", "IGNORE")],
                value="REPLACE",
                id="write-mode-select"
            )
            yield Label("Selected: 0 tables | Est. rows: 0", id="stats-label")
            yield Button("← Back", id="back-btn")
            yield Button("Start Migration →", variant="success", id="start-btn", disabled=True)

        yield Footer()

    def on_mount(self) -> None:
        self.load_metadata()

    @work(exclusive=True, thread=True)
    def load_metadata(self) -> None:
        """Fetch metadata from both hosts in background."""
        worker = get_current_worker()
        table_list = self.query_one("#table-list", DataTable)

        def prepare_list():
            table_list.loading = True
            table_list.clear(columns=True)
            table_list.add_columns("✓", "Table Name", "Rows", "Size", "Schema")

        self.app.call_from_thread(prepare_list)

        try:
            with get_connection(self.app.source_config) as source_conn:
                source_tables = get_tables(source_conn, self.app.source_config.database)

            if worker.is_cancelled:
                return

            with get_connection(self.app.target_config) as target_conn:
                target_tables = {t.name: t for t in get_tables(target_conn, self.app.target_config.database)}

            if worker.is_cancelled:
                return

            self.tables_data = source_tables

            def add_tables():
                for table in source_tables:
                    # Basic diff (existence Check)
                    schema_status = "✅ Match"
                    if table.name not in target_tables:
                        schema_status = "❌ Missing in Target"

                    self.schema_status[table.name] = schema_status

                    row_data = [
                        "[ ]",
                        table.name,
                        f"{table.row_count:,}",
                        format_size(table.data_size_bytes),
                        schema_status
                    ]
                    table_list.add_row(*row_data, key=table.name)

            self.app.call_from_thread(add_tables)

        except Exception as e:
            import logging
            from ...logging_setup import log_exception
            log_exception(
                logging.getLogger("pysync_maria.tui.table_select"),
                "load_metadata failed",
                e,
                screen="TableSelectScreen",
                phase="load_metadata"
            )
            self.app.call_from_thread(self.notify, f"Metadata error: {e!s}", severity="error")
        finally:
            self.app.call_from_thread(setattr, table_list, "loading", False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Toggle selection on row click/enter."""
        table_name = str(event.row_key.value)
        if table_name in self.selected_tables:
            self.selected_tables.remove(table_name)
            self.query_one("#table-list").update_cell(event.row_key, "✓", "[ ]")
        else:
            self.selected_tables.add(table_name)
            self.query_one("#table-list").update_cell(event.row_key, "✓", "[✓]")

        self.update_stats()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter table list in real-time."""
        if event.input.id == "table-filter":
            self.apply_filter(event.value.lower())

    def apply_filter(self, search_text: str) -> None:
        table_list = self.query_one("#table-list", DataTable)
        table_list.clear()

        for table in self.tables_data:
            if search_text and search_text not in table.name.lower():
                continue

            status = "[✓]" if table.name in self.selected_tables else "[ ]"
            schema = self.schema_status.get(table.name, "—")

            row_data = [
                status,
                table.name,
                f"{table.row_count:,}",
                format_size(table.data_size_bytes),
                schema
            ]
            table_list.add_row(*row_data, key=table.name)

        self.update_stats()

    def update_stats(self) -> None:
        """Update the footer selection statistics."""
        num_selected = len(self.selected_tables)
        total_rows = sum(
            t.row_count
            for t in self.tables_data
            if t.name in self.selected_tables
        )
        self.query_one("#stats-label", Label).update(
            f"Selected: {num_selected} tables | Est. rows: {total_rows:,}"
        )
        self.query_one("#start-btn", Button).disabled = num_selected == 0

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "start-btn":
            self.open_confirmation()

    def open_confirmation(self) -> None:
        selected_table_infos = [t for t in self.tables_data if t.name in self.selected_tables]

        self.app.push_screen(
            ConfirmModal(
                tables=selected_table_infos,
                source_db=self.app.source_config.database,
                target_db=self.app.target_config.database,
                mode=self.query_one("#write-mode-select", Select).value,
                dry_run=self.app.settings.dry_run,
                batch_size=self.app.settings.batch_size
            ),
            callback=self.handle_confirmation
        )

    def handle_confirmation(self, confirmed: bool) -> None:
        if confirmed:
            selected_table_infos = [t for t in self.tables_data if t.name in self.selected_tables]
            self.app.push_screen(
                MigrationScreen(
                    selected_tables=selected_table_infos,
                    mappings=self.table_mappings,
                    mode=self.query_one("#write-mode-select", Select).value,
                    dry_run=self.app.settings.dry_run,
                    batch_size=self.app.settings.batch_size
                )
            )

    BINDINGS = [
        ("space", "toggle_selection", "Toggle Selection"),
        ("a", "toggle_all", "Select All"),
        ("m", "open_mapping", "Custom Mapping"),
        ("r", "load_metadata", "Reload Statistics"),
    ]

    def action_open_mapping(self) -> None:
        """Open mapping modal for currently selected table."""
        table_list = self.query_one("#table-list", DataTable)
        if table_list.cursor_row is None:
            return

        row_key = list(table_list.rows.keys())[table_list.cursor_row]
        table_name = str(row_key.value)

        self.run_worker(self.fetch_and_open_mapping(table_name))

    async def fetch_and_open_mapping(self, table_name: str) -> None:
        """Fetch columns and open modal (Fix for E3)."""
        try:
            import asyncio
            # Wrap sync DB calls in to_thread to avoid blocking event loop
            def fetch_cols():
                with get_connection(self.app.source_config) as s_conn:
                    s_cols = get_columns(s_conn, self.app.source_config.database, table_name)
                with get_connection(self.app.target_config) as t_conn:
                    t_cols = get_columns(t_conn, self.app.target_config.database, table_name)
                return s_cols, t_cols

            s_cols, t_cols = await asyncio.to_thread(fetch_cols)

            self.app.push_screen(
                MappingModal(
                    table_name=table_name,
                    source_cols=s_cols,
                    target_cols=t_cols,
                    current_mapping=self.table_mappings.get(table_name)
                ),
                callback=lambda mapping: self.save_mapping(table_name, mapping)
            )
        except Exception as e:
            import logging
            from ...logging_setup import log_exception
            log_exception(
                logging.getLogger("pysync_maria.tui.table_select"),
                "Mapping fetch error",
                e,
                table=table_name
            )
            self.notify(f"Mapping fetch error: {e}", severity="error")

    def save_mapping(self, table_name: str, mapping: dict | None) -> None:
        if mapping:
            self.table_mappings[table_name] = mapping
            self.notify(f"Mapping saved for {table_name}")
            # Update schema status in table
            self.query_one("#table-list").update_cell(table_name, "Schema", "⚙️ Custom")

    def action_toggle_selection(self) -> None:
        table_list = self.query_one("#table-list", DataTable)
        if table_list.cursor_row is not None:
             row_key = list(table_list.rows.keys())[table_list.cursor_row]
             self._toggle_row(row_key)

    def action_toggle_all(self) -> None:
        table_list = self.query_one("#table-list", DataTable)
        all_keys = list(table_list.rows.keys())
        if len(self.selected_tables) == len(all_keys):
            self.selected_tables.clear()
            for key in all_keys:
                table_list.update_cell(key, "✓", "[ ]")
        else:
            for key in all_keys:
                self.selected_tables.add(str(key.value))
                table_list.update_cell(key, "✓", "[✓]")
        self.update_stats()

    def _toggle_row(self, row_key) -> None:
        table_name = str(row_key.value)
        table_list = self.query_one("#table-list", DataTable)
        if table_name in self.selected_tables:
            self.selected_tables.remove(table_name)
            table_list.update_cell(row_key, "✓", "[ ]")
        else:
            self.selected_tables.add(table_name)
            table_list.update_cell(row_key, "✓", "[✓]")
        self.update_stats()
