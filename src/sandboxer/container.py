"""Podman container operations for sandboxer."""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMAGE = "docker.io/rdubwiley/sandboxer"
MOUNT_TARGET = "/home/developer/project"
LABEL_MANAGED = "com.sandboxer.managed"
LABEL_MOUNTED_PATH = "com.sandboxer.mounted-path"


def _generate_dev_only_firewall_script() -> str:
    """Generate a shell script to set up iptables for dev-only access (Claude + package managers)."""
    return """
# Allowed domains for dev mode
ALLOWED_DOMAINS="
api.anthropic.com
pypi.org
files.pythonhosted.org
registry.npmjs.org
npmjs.com
proxy.golang.org
sum.golang.org
storage.googleapis.com
github.com
api.github.com
objects.githubusercontent.com
raw.githubusercontent.com
astral.sh
bun.sh
"

# Allow loopback
sudo iptables -A OUTPUT -o lo -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (needed for ongoing resolution)
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow HTTPS to each allowed domain
for domain in $ALLOWED_DOMAINS; do
    DOMAIN_IPS=$(getent ahostsv4 $domain 2>/dev/null | awk '{print $1}' | sort -u)
    for ip in $DOMAIN_IPS; do
        sudo iptables -A OUTPUT -p tcp --dport 443 -d $ip -j ACCEPT
    done
done

# Drop everything else
sudo iptables -A OUTPUT -j DROP

# Disable Claude web search by creating user settings
mkdir -p ~/.claude
cat > ~/.claude/settings.json << 'SETTINGS_EOF'
{
  "permissions": {
    "deny": ["WebSearch", "WebFetch"]
  }
}
SETTINGS_EOF
"""


def _generate_claude_only_firewall_script() -> str:
    """Generate a shell script to set up iptables for Claude API only access."""
    return """
# Resolve Claude API IPs (IPv4 only - filter out IPv6)
CLAUDE_IPS=$(getent ahostsv4 api.anthropic.com | awk '{print $1}' | sort -u)

# Allow loopback
sudo iptables -A OUTPUT -o lo -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (needed for ongoing resolution)
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow HTTPS to Claude API IPs
for ip in $CLAUDE_IPS; do
    sudo iptables -A OUTPUT -p tcp --dport 443 -d $ip -j ACCEPT
done

# Drop everything else
sudo iptables -A OUTPUT -j DROP

# Disable Claude web search by creating user settings
mkdir -p ~/.claude
cat > ~/.claude/settings.json << 'SETTINGS_EOF'
{
  "permissions": {
    "deny": ["WebSearch", "WebFetch"]
  }
}
SETTINGS_EOF
"""


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
    only_claude: bool = False,
    only_dev: bool = False,
) -> subprocess.CompletedProcess | None:
    """Run a container with the specified folder mounted.

    Args:
        folder_path: Absolute path to the folder to mount
        image: Container image to use
        detach: If True, run in detached mode with sleep infinity
        name: Container name (auto-generated if not provided)
        mount_target: Path inside the container where the folder will be mounted
        no_internet: If True, disable network access in the container
        only_claude: If True, restrict network to Claude API only
        only_dev: If True, restrict network to Claude API + package managers

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

    # Determine the final command to run
    if only_claude or only_dev:
        if only_dev:
            firewall_script = _generate_dev_only_firewall_script()
        else:
            firewall_script = _generate_claude_only_firewall_script()
        if detach:
            final_cmd = f"{firewall_script}\nexec sleep infinity"
        else:
            final_cmd = f"{firewall_script}\nexec bash"
        cmd.extend(["sh", "-c", final_cmd])
    else:
        if detach:
            cmd.extend(["sleep", "infinity"])
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
