import logging
import os
from pathlib import Path
from textual.app import App
from textual.binding import Binding
from typing import Optional
from ..config.settings import AppSettings, HostConfig
from .screens.connection_screen import ConnectionScreen
from .modals.help_modal import HelpModal
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
        self.source_config: HostConfig = settings.source
        self.target_config: HostConfig = settings.target
        self._setup_logging()

    def _setup_logging(self):
        log_dir = Path.home() / ".pysync-maria"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "pysync.log"
        
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        self.logger = logging.getLogger("pysync_maria")
        self.logger.info("Application started")

    def on_error(self, event) -> None:
        """Global error handler."""
        self.logger.critical(f"Unhandled exception: {event.exception}", exc_info=event.exception)
        self.notify("A critical error occurred. Check ~/.pysync-maria/pysync.log", severity="error")

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
        Binding("q", "quit", "Quit", show=True),
        Binding("d", "toggle_dry_run", "Toggle Dry Run"),
        Binding("f1", "help", "Help", show=True),
        Binding("question_mark", "help", "Help", show=False),
    ]
    
    def action_help(self) -> None:
        self.push_screen(HelpModal())
