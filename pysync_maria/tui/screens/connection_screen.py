from pydantic import SecretStr
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from ...config.settings import HostConfig
from ...db.connection import get_connection


class HostConnectionForm(Vertical):
    """A form representing a single host connection setup."""
    def __init__(self, title: str, config: HostConfig, id: str):
        super().__init__(id=id, classes="connection-column")
        self.title = title
        self.config = config

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="column-title")
        yield Input(placeholder="Hostname / IP", value=self.config.host, id="host")
        yield Input(placeholder="Port", value=str(self.config.port), id="port")
        yield Input(placeholder="Username", value=self.config.user, id="user")
        yield Input(
            placeholder="Password",
            value=self.config.password.get_secret_value(),
            password=True,
            id="password"
        )
        yield Input(placeholder="Database", value=self.config.database, id="database")

        yield Horizontal(
            Button("Test Connection", variant="primary", id="test-btn"),
            classes="button-row"
        )
        yield Label("Status: ○ Untested", id="status", classes="status-label")

class ConnectionScreen(Screen):
    """Screen for configuring and testing database connections."""

    source_ok: bool = False
    target_ok: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Connection Setup", id="connection-title")

        with Container(), Horizontal():
            yield HostConnectionForm("SOURCE (HOST A)", self.app.source_config, id="source-form")
            yield HostConnectionForm("TARGET (HOST B)", self.app.target_config, id="target-form")

        with Horizontal(classes="button-row"):
            yield Button("Connect & Proceed →", variant="success", id="connect-btn", disabled=True)

        yield Footer()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Invalidate connection status when any input changes."""
        form = event.input.parent
        if form.id == "source-form":
            self.source_ok = False
        elif form.id == "target-form":
            self.target_ok = False

        # Reset status label to untested
        status_label = form.query_one("#status", Label)
        status_label.update("Status: ○ Untested")
        self.check_all_ready()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test-btn":
            # Determine which form was pressed
            form = event.button.parent.parent
            self.test_connection(form)
        elif event.button.id == "connect-btn":
            self.app.push_screen("table_select")

    @work(exclusive=True, thread=True)
    def test_connection(self, form: HostConnectionForm) -> None:
        """Test connection in a background thread."""
        def update_status(text: str, color: str = "") -> None:
            status_label = form.query_one("#status", Label)
            if color:
                status_label.update(f"Status: [{color}]{text}[/]")
            else:
                status_label.update(f"Status: {text}")

        self.app.call_from_thread(update_status, "⏳ Connecting...", "yellow")

        try:
            # Update config from inputs
            config = HostConfig(
                host=form.query_one("#host", Input).value,
                port=int(form.query_one("#port", Input).value),
                user=form.query_one("#user", Input).value,
                password=SecretStr(form.query_one("#password", Input).value),
                database=form.query_one("#database", Input).value
            )

            with get_connection(config) as _:
                # Successfully connected
                self.app.call_from_thread(update_status, "✅ Connected", "green")

                # Thread-safe config commit and status update
                def commit_config():
                    if form.id == "source-form":
                        self.app.source_config = config
                        self.source_ok = True
                    else:
                        self.app.target_config = config
                        self.target_ok = True
                    self.check_all_ready()

                self.app.call_from_thread(commit_config)

        except Exception as e:
            import logging

            from ...logging_setup import log_exception
            log_exception(
                logging.getLogger("pysync_maria.connection"),
                "Test connection failed",
                e,
                form_id=form.id,
                host=form.query_one("#host", Input).value
            )

            def mark_failed():
                if form.id == "source-form":
                    self.source_ok = False
                else:
                    self.target_ok = False
                self.check_all_ready()

            self.app.call_from_thread(mark_failed)
            self.app.call_from_thread(update_status, f"❌ {str(e)[:40]}...", "red")

    def check_all_ready(self) -> None:
        """Enable the Connect button if both connections are verified."""
        self.query_one("#connect-btn", Button).disabled = not (
            self.source_ok and self.target_ok
        )
