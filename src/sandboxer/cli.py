"""Sandboxer CLI - Typer-based command interface."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from sandboxer import __version__
from sandboxer.container import (
    DEFAULT_IMAGE,
    MOUNT_TARGET,
    attach_container,
    list_containers,
    remove_container,
    run_container,
    stop_container,
)

app = typer.Typer(
    name="sandboxer",
    help="A CLI tool for sandboxing folders into containers.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"sandboxer version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Sandboxer - A CLI tool for sandboxing folders into containers."""
    pass


@app.command()
def run(
    folder: Annotated[
        Path,
        typer.Argument(
            help="Folder path to mount in the container.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    image: Annotated[
        str,
        typer.Option("--image", "-i", help="Container image to use."),
    ] = DEFAULT_IMAGE,
    detach: Annotated[
        bool,
        typer.Option("--detach", "-d", help="Run container in detached mode."),
    ] = False,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Container name (auto-generated if not provided)."),
    ] = None,
    container_dir: Annotated[
        str,
        typer.Option("--container-dir", "-c", help="Directory inside the container to mount the folder to."),
    ] = MOUNT_TARGET,
) -> None:
    """Run a sandboxed container with the specified folder mounted."""
    folder = folder.resolve()

    if detach:
        console.print(f"Starting container with [cyan]{folder}[/cyan] mounted at [cyan]{container_dir}[/cyan]...")
        result = run_container(folder, image=image, detach=True, name=name, mount_target=container_dir)
        if result and result.returncode == 0:
            container_id = result.stdout.strip()[:12]
            console.print(f"[green]Container started:[/green] {container_id}")
        elif result:
            console.print(f"[red]Error:[/red] {result.stderr}", err=True)
            raise typer.Exit(1)
    else:
        console.print(f"Starting interactive container with [cyan]{folder}[/cyan] mounted at [cyan]{container_dir}[/cyan]...")
        console.print("Type 'exit' to leave the container.\n")
        run_container(folder, image=image, detach=False, name=name, mount_target=container_dir)


@app.command("list")
def list_cmd(
    running: Annotated[
        bool,
        typer.Option("--running", "-r", help="Only show running containers."),
    ] = False,
) -> None:
    """List sandboxer-managed containers."""
    containers = list_containers(running_only=running)

    if not containers:
        console.print("[yellow]No sandboxer containers found.[/yellow]")
        return

    table = Table(title="Sandboxer Containers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Mounted Folder", style="blue")

    for container in containers:
        table.add_row(
            container.id,
            container.name,
            container.status,
            container.mounted_path,
        )

    console.print(table)


@app.command()
def stop(
    container: Annotated[
        str,
        typer.Argument(help="Container name or ID to stop."),
    ],
) -> None:
    """Stop a sandboxer container."""
    console.print(f"Stopping container [cyan]{container}[/cyan]...")
    result = stop_container(container)
    if result.returncode == 0:
        console.print(f"[green]Container stopped.[/green]")
    else:
        console.print(f"[red]Error:[/red] {result.stderr}", err=True)
        raise typer.Exit(1)


@app.command()
def rm(
    container: Annotated[
        str,
        typer.Argument(help="Container name or ID to remove."),
    ],
) -> None:
    """Remove a sandboxer container."""
    console.print(f"Removing container [cyan]{container}[/cyan]...")
    result = remove_container(container)
    if result.returncode == 0:
        console.print(f"[green]Container removed.[/green]")
    else:
        console.print(f"[red]Error:[/red] {result.stderr}", err=True)
        raise typer.Exit(1)


@app.command()
def attach(
    container: Annotated[
        str,
        typer.Argument(help="Container name or ID to attach to."),
    ],
) -> None:
    """Attach to a running sandboxer container."""
    console.print(f"Attaching to container [cyan]{container}[/cyan]...")
    console.print("Type 'exit' to leave the container.\n")
    attach_container(container)


if __name__ == "__main__":
    app()
