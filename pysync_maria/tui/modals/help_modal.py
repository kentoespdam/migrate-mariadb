from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Static
from textual.containers import Container, Vertical, Horizontal

class HelpModal(ModalScreen):
    """Modal for displaying keyboard shortcuts."""
    
    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("PySync-Maria: Keyboard shortcuts", id="modal-title")
            
            with Vertical(id="help-content"):
                yield Label("[bold]Global[/]")
                yield Label("  [cyan]Q[/]       - Quit App (Confirmation)")
                yield Label("  [cyan]? / F1[/]  - Show this Help")
                yield Label("  [cyan]D[/]       - Toggle Dry Run Mode")
                yield Static()
                yield Label("[bold]Table Selection[/]")
                yield Label("  [cyan]Space[/]   - Toggle selection")
                yield Label("  [cyan]A[/]       - Select/Deselect All")
                yield Label("  [cyan]M[/]       - Custom Column Mapping")
                yield Label("  [cyan]R[/]       - Reload Metadata")
                yield Static()
                yield Label("[bold]Migration[/]")
                yield Label("  [cyan]P[/]       - Pause / Resume")
                yield Label("  [cyan]C[/]       - Cancel Migration")
                yield Label("  [cyan]E[/]       - Export Migration Log")
            
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", id="close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
