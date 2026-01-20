"""Integration tests for sandboxer CLI."""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from sandboxer.container import (
    LABEL_MANAGED,
    LABEL_MOUNTED_PATH,
    MOUNT_TARGET,
    exec_in_container,
    generate_container_name,
    inspect_container,
    list_containers,
    remove_container,
    run_container,
    stop_container,
)


@pytest.fixture
def temp_folder():
    """Create a temporary folder for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def container_cleanup():
    """Fixture to track and cleanup containers after tests."""
    containers_to_cleanup = []

    yield containers_to_cleanup

    for container_name in containers_to_cleanup:
        stop_container(container_name)
        remove_container(container_name)


class TestContainerOperations:
    """Test container operations."""

    def test_generate_container_name(self, temp_folder):
        """Test container name generation."""
        name = generate_container_name(temp_folder)
        assert name.startswith("sandboxer-")
        assert temp_folder.name in name
        assert len(name.split("-")[-1]) == 8

    def test_run_creates_container(self, temp_folder, container_cleanup):
        """Test that running a container creates it successfully."""
        container_name = generate_container_name(temp_folder)
        container_cleanup.append(container_name)

        result = run_container(temp_folder, detach=True)

        assert result is not None
        assert result.returncode == 0

        ps_result = subprocess.run(
            ["podman", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        assert container_name in ps_result.stdout

    def test_list_shows_container(self, temp_folder, container_cleanup):
        """Test that list_containers shows the running container."""
        container_name = generate_container_name(temp_folder)
        container_cleanup.append(container_name)

        run_container(temp_folder, detach=True)

        time.sleep(1)

        containers = list_containers(running_only=True)
        container_names = [c.name for c in containers]
        assert container_name in container_names

        container = next(c for c in containers if c.name == container_name)
        assert container.mounted_path == str(temp_folder)

    def test_mount_bidirectional(self, temp_folder, container_cleanup):
        """Test that files can be created and seen from both host and container."""
        container_name = generate_container_name(temp_folder)
        container_cleanup.append(container_name)

        run_container(temp_folder, detach=True)

        time.sleep(1)

        host_file = temp_folder / "host_created.txt"
        host_file.write_text("created on host")

        result = exec_in_container(
            container_name,
            ["cat", f"{MOUNT_TARGET}/host_created.txt"],
        )
        assert result.returncode == 0
        assert "created on host" in result.stdout

        exec_in_container(
            container_name,
            ["sh", "-c", f"echo 'created in container' > {MOUNT_TARGET}/container_created.txt"],
        )

        container_file = temp_folder / "container_created.txt"
        assert container_file.exists()
        assert "created in container" in container_file.read_text()

    def test_container_labels(self, temp_folder, container_cleanup):
        """Test that container has correct labels."""
        container_name = generate_container_name(temp_folder)
        container_cleanup.append(container_name)

        run_container(temp_folder, detach=True)

        result = inspect_container(container_name)
        assert result.returncode == 0

        inspect_data = json.loads(result.stdout)
        labels = inspect_data[0]["Config"]["Labels"]

        assert labels.get(LABEL_MANAGED) == "true"
        assert labels.get(LABEL_MOUNTED_PATH) == str(temp_folder)

    def test_default_folder(self, container_cleanup):
        """Test that running without folder arg uses current directory."""
        current_dir = Path.cwd()
        container_name = generate_container_name(current_dir)
        container_cleanup.append(container_name)

        result = run_container(current_dir, detach=True)

        assert result is not None
        assert result.returncode == 0

        inspect_result = inspect_container(container_name)
        inspect_data = json.loads(inspect_result.stdout)
        labels = inspect_data[0]["Config"]["Labels"]

        assert labels.get(LABEL_MOUNTED_PATH) == str(current_dir)

    def test_stop_container(self, temp_folder, container_cleanup):
        """Test stopping a container."""
        container_name = generate_container_name(temp_folder)
        container_cleanup.append(container_name)

        run_container(temp_folder, detach=True)
        time.sleep(1)

        result = stop_container(container_name)
        assert result.returncode == 0

        containers = list_containers(running_only=True)
        container_names = [c.name for c in containers]
        assert container_name not in container_names

    def test_remove_container(self, temp_folder, container_cleanup):
        """Test removing a container."""
        container_name = generate_container_name(temp_folder)

        run_container(temp_folder, detach=True)
        time.sleep(1)

        stop_container(container_name)
        result = remove_container(container_name)
        assert result.returncode == 0

        containers = list_containers(running_only=False)
        container_names = [c.name for c in containers]
        assert container_name not in container_names
