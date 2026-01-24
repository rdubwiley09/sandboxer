"""Podman container operations for sandboxer."""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMAGE = "rdubwiley/sandboxer"
MOUNT_TARGET = "/home/developer/project"
LABEL_MANAGED = "com.sandboxer.managed"
LABEL_MOUNTED_PATH = "com.sandboxer.mounted-path"


def pull_image(image: str) -> subprocess.CompletedProcess:
    """Pull a container image with visible progress.

    Args:
        image: Container image to pull

    Returns:
        CompletedProcess with the result
    """
    # Don't capture stdout so progress is visible, but capture stderr for errors
    return subprocess.run(["podman", "pull", image], stderr=subprocess.PIPE, text=True)


@dataclass
class Container:
    """Represents a sandboxer-managed container."""

    id: str
    name: str
    status: str
    mounted_path: str


def generate_container_name(folder_path: Path) -> str:
    """Generate a unique container name based on folder path.

    Format: sandboxer-{folder_basename}-{sha256(path)[:8]}
    """
    folder_name = folder_path.name
    path_hash = hashlib.sha256(str(folder_path).encode()).hexdigest()[:8]
    return f"sandboxer-{folder_name}-{path_hash}"


def run_container(
    folder_path: Path,
    image: str = DEFAULT_IMAGE,
    detach: bool = False,
    name: str | None = None,
    mount_target: str = MOUNT_TARGET,
    no_internet: bool = False,
) -> subprocess.CompletedProcess | None:
    """Run a container with the specified folder mounted.

    Args:
        folder_path: Absolute path to the folder to mount
        image: Container image to use
        detach: If True, run in detached mode with sleep infinity
        name: Container name (auto-generated if not provided)
        mount_target: Path inside the container where the folder will be mounted
        no_internet: If True, disable network access in the container

    Returns:
        CompletedProcess for detached mode, None for interactive mode
    """
    if name is None:
        name = generate_container_name(folder_path)

    cmd = ["podman", "run", "--replace"]

    if no_internet:
        cmd.append("--network=none")

    if detach:
        cmd.append("-d")
    else:
        cmd.extend(["-it"])

    cmd.extend(
        [
            "--name",
            name,
            "--userns=keep-id",
            "--privileged",
            "--label",
            f"{LABEL_MANAGED}=true",
            "--label",
            f"{LABEL_MOUNTED_PATH}={folder_path}",
            "-v",
            f"{folder_path}:{mount_target}",
            "-w",
            mount_target,
            image,
        ]
    )

    if detach:
        cmd.append("sleep")
        cmd.append("infinity")
    else:
        cmd.append("bash")

    if detach:
        # Pull image first with visible progress to avoid appearing frozen
        pull_result = pull_image(image)
        if pull_result.returncode != 0:
            return pull_result
        return subprocess.run(cmd, capture_output=True, text=True)
    else:
        subprocess.run(cmd)
        return None


def list_containers(running_only: bool = False) -> list[Container]:
    """List sandboxer-managed containers.

    Args:
        running_only: If True, only list running containers

    Returns:
        List of Container objects
    """
    cmd = [
        "podman",
        "ps",
        "--filter",
        f"label={LABEL_MANAGED}=true",
        "--format",
        "{{.ID}}|{{.Names}}|{{.Status}}|{{.Labels}}",
    ]

    if not running_only:
        cmd.append("-a")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|")
        if len(parts) < 4:
            continue

        container_id = parts[0]
        name = parts[1]
        status = parts[2]
        labels = parts[3]

        mounted_path = ""
        # Labels format: map[key:value key2:value2 ...]
        if labels.startswith("map[") and labels.endswith("]"):
            labels_content = labels[4:-1]
            for label in labels_content.split(" "):
                if label.startswith(f"{LABEL_MOUNTED_PATH}:"):
                    mounted_path = label.split(":", 1)[1]
                    break

        containers.append(
            Container(
                id=container_id[:12],
                name=name,
                status=status,
                mounted_path=mounted_path,
            )
        )

    return containers


def stop_container(name_or_id: str) -> subprocess.CompletedProcess:
    """Stop a container by name or ID."""
    return subprocess.run(
        ["podman", "stop", name_or_id],
        capture_output=True,
        text=True,
    )


def remove_container(name_or_id: str) -> subprocess.CompletedProcess:
    """Remove a container by name or ID."""
    return subprocess.run(
        ["podman", "rm", name_or_id],
        capture_output=True,
        text=True,
    )


def attach_container(name_or_id: str) -> None:
    """Exec into a running container."""
    subprocess.run(["podman", "exec", "-it", name_or_id, "bash"])


def exec_in_container(
    name_or_id: str, command: list[str]
) -> subprocess.CompletedProcess:
    """Execute a command in a container and return the result."""
    return subprocess.run(
        ["podman", "exec", name_or_id] + command,
        capture_output=True,
        text=True,
    )


def find_container_by_name(name: str) -> Container | None:
    """Find a container by name (running or stopped).

    Args:
        name: Container name to search for

    Returns:
        Container object if found, None otherwise
    """
    containers = list_containers(running_only=False)
    for container in containers:
        if container.name == name:
            return container
    return None


def inspect_container(name_or_id: str) -> subprocess.CompletedProcess:
    """Inspect a container and return JSON data."""
    return subprocess.run(
        ["podman", "inspect", name_or_id],
        capture_output=True,
        text=True,
    )
