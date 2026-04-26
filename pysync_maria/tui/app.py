import logging
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from ..config.settings import AppSettings, HostConfig
from .modals.help_modal import HelpModal
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
        self.source_config: HostConfig = settings.source
        self.target_config: HostConfig = settings.target
        self.logger = logging.getLogger("pysync_maria")

    def on_error(self, event) -> None:
        """Global error handler."""
        from ..logging_setup import log_exception
        log_exception(self.logger, "Textual on_error", event.exception, screen=str(self.screen))
        self.notify("A critical error occurred. Check logs/error.log", severity="error")

    def on_mount(self) -> None:
        """Start with the connection screen."""
        import asyncio
        from ..logging_setup import attach_asyncio_handler
        attach_asyncio_handler(asyncio.get_running_loop())
        
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
