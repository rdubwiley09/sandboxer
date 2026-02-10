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
    exec_in_container,
    find_container_by_name,
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
            "--version",
            "-v",
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
        typer.Option(
            "--name", "-n", help="Container name (auto-generated if not provided)."
        ),
    ] = None,
    container_dir: Annotated[
        str,
        typer.Option(
            "--container-dir",
            "-c",
            help="Directory inside the container to mount the folder to.",
        ),
    ] = MOUNT_TARGET,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Skip confirmation prompts when removing stopped containers.",
        ),
    ] = False,
    no_internet: Annotated[
        bool,
        typer.Option(
            "--no-internet",
            help="Disable network access in the container.",
        ),
    ] = False,
    only_claude: Annotated[
        bool,
        typer.Option(
            "--only-claude",
            help="Restrict network access to Claude API only.",
        ),
    ] = False,
    only_dev: Annotated[
        bool,
        typer.Option(
            "--only-dev",
            help="Restrict network to Claude API + package managers (uv, bun, go).",
        ),
    ] = False,
    engine: Annotated[
        str,
        typer.Option(
            "--engine",
            help="Container engine to use (podman or docker).",
        ),
    ] = "podman",
    expose_ports: Annotated[
        bool,
        typer.Option(
            "--expose-ports/--no-expose-ports",
            help="Enable or disable port mapping from container to host.",
        ),
    ] = True,
    ports: Annotated[
        Optional[list[int]],
        typer.Option(
            "--ports",
            help="Ports to expose from the container (default: 3000). Can be specified multiple times.",
        ),
    ] = None,
) -> None:
    """Run a sandboxed container with the specified folder mounted."""
    # Validate engine parameter
    if engine not in ("podman", "docker"):
        console.print(
            "[red]Error:[/red] --engine must be either 'podman' or 'docker'."
        )
        raise typer.Exit(1)

    network_flags = sum([no_internet, only_claude, only_dev])
    if network_flags > 1:
        console.print(
            "[red]Error:[/red] --no-internet, --only-claude, and --only-dev are mutually exclusive."
        )
        raise typer.Exit(1)

    if expose_ports and no_internet:
        console.print(
            "[yellow]Warning:[/yellow] --expose-ports has no effect with --no-internet. Port mapping disabled."
        )
        expose_ports = False

    folder = folder.resolve()

    # Generate container name if not provided
    if name is None:
        from sandboxer.container import generate_container_name

        name = generate_container_name(folder)

    # Check if container with this name already exists
    existing_container = find_container_by_name(name, engine=engine)

    if existing_container:
        # Check if container is running
        if (
            "Up" in existing_container.status
            or "running" in existing_container.status.lower()
        ):
            # Container is running - attach to it
            if existing_container.mounted_path and str(
                existing_container.mounted_path
            ) != str(folder):
                console.print(
                    f"[yellow]Warning:[/yellow] Running container '{name}' is mounted to '{existing_container.mounted_path}' but you requested '{folder}'."
                )
                console.print("Connecting anyway...\n")
            else:
                console.print(
                    f"Found running container '{name}'. Connecting to it...\n"
                )

            if detach:
                console.print(f"[green]Container '{name}' is already running.[/green]")
                console.print(f"Container ID: {existing_container.id}")
            else:
                attach_container(name, engine=engine)
            return

        # Container is stopped - ask for confirmation to remove it
        console.print(f"Found stopped container '{name}' with the same name.")

        if force:
            console.print("Removing stopped container (force flag used)...")
            remove_result = remove_container(name, engine=engine)
            if remove_result.returncode != 0:
                console.print(
                    f"[red]Error removing stopped container:[/red] {remove_result.stderr}",
                    err=True,
                )
                raise typer.Exit(1)
        else:
            # Ask for user confirmation
            response = typer.confirm("Remove it and create a new one?")
            if not response:
                console.print("Operation cancelled.")
                raise typer.Exit(0)

            remove_result = remove_container(name, engine=engine)
            if remove_result.returncode != 0:
                console.print(
                    f"[red]Error removing stopped container:[/red] {remove_result.stderr}",
                    err=True,
                )
                raise typer.Exit(1)

    # Proceed with container creation
    if detach:
        console.print(
            f"Starting container with [cyan]{folder}[/cyan] mounted at [cyan]{container_dir}[/cyan]..."
        )
        result = run_container(
            folder, image=image, detach=True, name=name, mount_target=container_dir,
            no_internet=no_internet, only_claude=only_claude, only_dev=only_dev,
            engine=engine, expose_ports=expose_ports, ports=ports
        )
        if result and result.returncode == 0:
            container_id = result.stdout.strip()[:12]
            console.print(f"[green]Container started:[/green] {container_id}")
        elif result:
            console.print(f"[red]Error:[/red] {result.stderr}", err=True)
            raise typer.Exit(1)
    else:
        console.print(
            f"Starting interactive container with [cyan]{folder}[/cyan] mounted at [cyan]{container_dir}[/cyan]..."
        )
        console.print("Type 'exit' to leave the container.\n")
        run_container(
            folder, image=image, detach=False, name=name, mount_target=container_dir,
            no_internet=no_internet, only_claude=only_claude, only_dev=only_dev,
            engine=engine, expose_ports=expose_ports, ports=ports
        )


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


@app.command()
def turn_off_claude_websearch(
    container: Annotated[
        str,
        typer.Argument(help="Container name or ID to configure."),
    ],
) -> None:
    """Disable Claude Code web search tools in a container."""
    console.print(
        f"Disabling Claude web search in container [cyan]{container}[/cyan]..."
    )

    # Use claude config to disable web search
    result = exec_in_container(
        container,
        ["claude", "config", "set", "webSearch", "false"],
    )

    if result.returncode == 0:
        console.print("[green]Claude web search disabled.[/green]")
    else:
        console.print(f"[red]Error:[/red] {result.stderr}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
