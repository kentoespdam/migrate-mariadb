from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Button, Label, Static
from textual.containers import Container, Horizontal, Vertical
from textual import work
from ...db.connection import get_connection, ConnectionError
from ...config.settings import HostConfig
from pydantic import SecretStr

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
        yield Input(placeholder="Password", value=self.config.password.get_secret_value(), password=True, id="password")
        yield Input(placeholder="Database", value=self.config.database, id="database")
        
        yield Horizontal(
            Button("Test Connection", variant="primary", id="test-btn"),
            classes="button-row"
        )
        yield Label("Status: ○ Untested", id="status", classes="status-label")

class ConnectionScreen(Screen):
    """Screen for configuring and testing database connections."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Connection Setup", id="connection-title")
        
        with Container():
            with Horizontal():
                yield HostConnectionForm("SOURCE (HOST A)", self.app.source_config, id="source-form")
                yield HostConnectionForm("TARGET (HOST B)", self.app.target_config, id="target-form")
        
        with Horizontal(classes="button-row"):
            yield Button("Connect & Proceed →", variant="success", id="connect-btn", disabled=True)
        
        yield Footer()

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
        status_label = form.query_one("#status", Label)
        self.app.call_from_thread(status_label.update, "Status: ⏳ Connecting...")
        
        try:
            # Update config from inputs
            config = HostConfig(
                host=form.query_one("#host", Input).value,
                port=int(form.query_one("#port", Input).value),
                user=form.query_one("#user", Input).value,
                password=SecretStr(form.query_one("#password", Input).value),
                database=form.query_one("#database", Input).value
            )
            
            with get_connection(config) as conn:
                version = "Connected" # We could fetch version if we want
                self.app.call_from_thread(status_label.update, f"Status: ✅ {version}")
                # Save the validated config
                if form.id == "source-form":
                    self.app.source_config = config
                else:
                    self.app.target_config = config
            
            self.app.call_from_thread(self.check_all_ready)
            
        except Exception as e:
            self.app.call_from_thread(status_label.update, f"Status: ❌ {str(e)[:40]}...")

    def check_all_ready(self) -> None:
        """Enable the Connect button if both connections are verified."""
        source_status = self.query_one("#source-form #status", Label).renderable
        target_status = self.query_one("#target-form #status", Label).renderable
        
        if "✅" in str(source_status) and "✅" in str(target_status):
            self.query_one("#connect-btn", Button).disabled = False
