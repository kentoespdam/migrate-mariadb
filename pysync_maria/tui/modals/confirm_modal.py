
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from ...db.metadata import TableInfo


class ConfirmModal(ModalScreen[bool]):
    """Modal for migration confirmation."""

    def __init__(self, tables: list[TableInfo], source_db: str, target_db: str, mode: str, dry_run: bool, batch_size: int):
        super().__init__()
        self.tables = tables
        self.source_db = source_db
        self.target_db = target_db
        self.mode = mode
        self.dry_run = dry_run
        self.batch_size = batch_size

    def compose(self) -> ComposeResult:
        total_rows = sum(t.row_count for t in self.tables)
        total_bytes = sum(t.data_size_bytes for t in self.tables)

        from ...db.metadata import format_size

        with Container(id="modal-container"):
            yield Label("⚠️ Confirm Migration", id="modal-title")

            with Vertical(id="confirm-summary"):
                yield Label(f"SOURCE : {self.source_db}")
                yield Label(f"TARGET : {self.target_db}")
                yield Static()
                yield Label(f"Tables : {len(self.tables)}")
                yield Label(f"Rows   : {total_rows:,}")
                yield Label(f"Size   : {format_size(total_bytes)}")
                yield Static()
                yield Label(f"Mode   : {self.mode}")
                yield Label(f"Batch  : {self.batch_size:,}")

            if not self.dry_run:
                yield Label("🚨 DRY RUN: OFF - Data will be WRITTEN to target!", classes="confirm-warning")
            else:
                yield Label("ℹ️ DRY RUN: ON - Simulation mode", classes="schema-match")

            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button("Start Migration", variant="success", id="start-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "start-btn":
            self.dismiss(True)
