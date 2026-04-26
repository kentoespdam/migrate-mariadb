from textual.app import App
from typing import Optional
from ..config.settings import AppSettings, HostConfig
from .screens.connection_screen import ConnectionScreen
from .screens.table_select_screen import TableSelectScreen

class PySyncMariaApp(App):
    """The main Textual application for PySync-Maria."""
    
    TITLE = "PySync-Maria"
    CSS_PATH = "app.tcss"
    
    SCREENS = {
        "connection": ConnectionScreen,
        "table_select": TableSelectScreen,
    }

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        # We'll update these as user interacts with ConnectionScreen
        self.source_config: HostConfig = settings.source
        self.target_config: HostConfig = settings.target

    def on_mount(self) -> None:
        """Start with the connection screen."""
        self.push_screen("connection")

    def action_toggle_dry_run(self) -> None:
        """Global action to toggle dry run mode."""
        self.settings.dry_run = not self.settings.dry_run
        self.notify(f"Dry Run Mode: {'ON' if self.settings.dry_run else 'OFF'}")
        
    def action_quit_app(self) -> None:
        """Global action to quit."""
        self.exit()

    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("d", "toggle_dry_run", "Toggle Dry Run"),
    ]
