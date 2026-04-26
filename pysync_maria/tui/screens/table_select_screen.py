from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Label, Button
from textual.containers import Container, Horizontal
from textual import work
from ...db.metadata import get_tables, get_columns, diff_columns, format_size
from ...db.connection import get_connection

class TableSelectScreen(Screen):
    """Screen for selecting tables to migrate."""

    def __init__(self):
        super().__init__()
        self.tables_data = []
        self.selected_tables = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Database Overview & Table Selection", id="connection-title")
        
        yield DataTable(id="table-list")
        
        with Horizontal(id="table-footer"):
            yield Label("Selected: 0 tables | Est. rows: 0", id="stats-label")
            yield Button("← Back", id="back-btn")
            yield Button("Start Migration →", variant="success", id="start-btn", disabled=True)
            
        yield Footer()

    def on_mount(self) -> None:
        self.load_metadata()

    @work(exclusive=True, thread=True)
    def load_metadata(self) -> None:
        """Fetch metadata from both hosts in background."""
        table_list = self.query_one("#table-list", DataTable)
        self.call_from_thread(table_list.loading, True)
        self.call_from_thread(lambda: table_list.clear(columns=True))
        
        self.call_from_thread(table_list.add_columns, "✓", "Table Name", "Rows", "Size", "Schema")

        try:
            with get_connection(self.app.source_config) as source_conn:
                source_tables = get_tables(source_conn, self.app.source_config.database)
                
            with get_connection(self.app.target_config) as target_conn:
                target_tables = {t.name: t for t in get_tables(target_conn, self.app.target_config.database)}

            self.tables_data = source_tables
            
            for table in source_tables:
                # Basic diff (existence Check)
                schema_status = "✅ Match"
                if table.name not in target_tables:
                    schema_status = "❌ Missing in Target"
                
                # In real app, we'd do full column diff here or on demand
                row_data = [
                    "[ ]", 
                    table.name, 
                    f"{table.row_count:,}", 
                    format_size(table.data_size_bytes),
                    schema_status
                ]
                self.call_from_thread(table_list.add_row, *row_data, key=table.name)

        except Exception as e:
            self.notify(f"Metadata error: {str(e)}", severity="error")
        finally:
            self.call_from_thread(setattr, table_list, "loading", False)

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

    def update_stats(self) -> None:
        """Update the footer selection statistics."""
        num_selected = len(self.selected_tables)
        total_rows = sum(t.row_count for t in self.tables_data if t.name in self.selected_tables)
        
        self.query_one("#stats-label").update(f"Selected: {num_selected} tables | Est. rows: {total_rows:,}")
        self.query_one("#start-btn").disabled = num_selected == 0

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "start-btn":
            self.notify("Migration starting in Phase 5...")

    BINDINGS = [
        ("space", "toggle_selection", "Toggle Selection"),
        ("a", "toggle_all", "Select All"),
    ]

    def action_toggle_selection(self) -> None:
        table_list = self.query_one("#table-list", DataTable)
        if table_list.cursor_row is not None:
             # Logic to toggle currently highlighted row
             pass # Will implement more robustly if needed
