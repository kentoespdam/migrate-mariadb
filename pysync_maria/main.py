import typer
from pathlib import Path
from typing import Optional
from typing_extensions import Annotated
from .config.settings import load_app_settings, AppSettings
from rich.console import Console

app = typer.Typer(
    help="PySync-Maria: Interactive CLI for MariaDB-to-MariaDB data migration",
    add_completion=False,
)
console = Console()

@app.command()
def main(
    source: Annotated[
        Path,
        typer.Option(
            "--source",
            exists=False, # We validate manually for better error message
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to .env file for Source Host (Host A)",
        ),
    ] = Path(".env.source"),
    target: Annotated[
        Path,
        typer.Option(
            "--target",
            exists=False,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to .env file for Target Host (Host B)",
        ),
    ] = Path(".env.target"),
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", min=1, max=100000, help="Batch size per iteration"),
    ] = 5000,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run in Dry Run mode (no data written to target)"),
    ] = False,
    version: Annotated[
        Optional[bool],
        typer.Option("--version", help="Show application version", is_flag=True),
    ] = None,
):
    """
    Launch the PySync-Maria TUI.
    """
    if version:
        console.print("PySync-Maria v0.1.0")
        raise typer.Exit()

    # Log parameters (simplified for now)
    # console.print(f"[bold blue]Initializing PySync-Maria...[/]")
    
    try:
        # Validate env files exist
        if not source.exists():
            console.print(f"[bold red]Error:[/] Source env file not found: {source}")
            raise typer.Exit(code=1)
        if not target.exists():
            console.print(f"[bold red]Error:[/] Target env file not found: {target}")
            raise typer.Exit(code=1)

        # Load settings
        settings = load_app_settings(source_env=source, target_env=target)
        
        # Override batch_size and dry_run from CLI
        settings.batch_size = batch_size
        settings.dry_run = dry_run

        console.print("[green]Configuration loaded successfully.[/]")
        console.print(f"Source Host: [cyan]{settings.source.host}[/]")
        console.print(f"Target Host: [cyan]{settings.target.host}[/]")
        
        # TODO: Phase 3 - Launch Textual TUI
        console.print("\n[yellow]TUI implementation coming soon in Phase 3...[/]")
        
    except Exception as e:
        console.print(f"[bold red]Configuration Error:[/] {str(e)}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
