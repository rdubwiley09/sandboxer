# Sandboxer

A CLI tool for sandboxing folders into containers using Podman. Perfect for isolating development environments with pre-configured tools like Claude Code, Go, Python, and Bun.

## Features

- Mount any local folder into an isolated container environment
- Pre-built container image with development tools ready to go
- Manage multiple sandbox containers (list, stop, attach, remove)
- Uses Podman for rootless container execution

## Container Image

The included Dockerfile builds an Ubuntu 24.04-based image with:

| Tool | Description |
|------|-------------|
| [Claude Code](https://claude.ai/claude-code) | Anthropic's CLI for Claude |
| [OpenCode](https://opencode.ai) | AI coding assistant |
| [uv](https://github.com/astral-sh/uv) | Fast Python package manager |
| [Bun](https://bun.sh) | Fast JavaScript runtime |
| [Go](https://go.dev) | Go programming language (v1.23.5) |
| [Pyright](https://github.com/microsoft/pyright) | Python type checker |
| ripgrep, jq, neovim, tmux | Developer utilities |

The image supports both `amd64` and `arm64` architectures.

## Building the Container Image

```bash
# Build for current architecture
podman build -t sandboxer .

# Build for a specific architecture
podman build --platform linux/amd64 -t sandboxer:amd64 .
podman build --platform linux/arm64 -t sandboxer:arm64 .

# Build multi-arch image and push to registry
podman build --platform linux/amd64,linux/arm64 -t myregistry/sandboxer:latest --manifest sandboxer .
podman manifest push sandboxer docker://myregistry/sandboxer:latest
```

## Installation

### Prerequisites

- [Podman](https://podman.io/docs/installation) installed on your system
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Install the CLI

```bash
# Using uv (recommended)
uv pip install .

# Or using pip
pip install .

# For development
uv pip install -e ".[dev]"
```

Alternatively, run the install script which sets up Podman, uv, and Claude Code:

```bash
./install.sh
```

## Usage

### Run a sandbox container

Mount the current directory into an interactive container:

```bash
sandboxer run
```

Mount a specific folder:

```bash
sandboxer run /path/to/project
```

Use a custom container image:

```bash
sandboxer run /path/to/project --image myregistry/custom-image:latest
```

Run in detached mode (background):

```bash
sandboxer run /path/to/project --detach
```

Specify a custom container name:

```bash
sandboxer run /path/to/project --name my-sandbox
```

Run without network access (isolated from the internet):

```bash
sandboxer run /path/to/project --no-internet
```

Run with Claude API access only (blocks all other internet traffic):

```bash
sandboxer run /path/to/project --only-claude
```

Run with Claude API + package manager access (for development):

```bash
sandboxer run /path/to/project --only-dev
```

### Network Restriction Modes

| Flag | Description |
|------|-------------|
| `--no-internet` | Complete network isolation. No internet access at all. |
| `--only-claude` | Only allows connections to the Claude API (api.anthropic.com). Useful for AI-assisted coding without external network access. |
| `--only-dev` | Allows Claude API plus common package registries for development work. |

The `--only-dev` flag allows access to:
- **Claude API**: api.anthropic.com
- **Python (uv/pip)**: pypi.org, files.pythonhosted.org
- **JavaScript (bun/npm)**: registry.npmjs.org, npmjs.com
- **Go**: proxy.golang.org, sum.golang.org, storage.googleapis.com
- **Tool updates**: github.com, api.github.com, objects.githubusercontent.com, raw.githubusercontent.com, astral.sh, bun.sh

Both `--only-claude` and `--only-dev` also disable Claude Code's WebSearch and WebFetch tools automatically.

These flags are mutually exclusive - you can only use one network restriction mode at a time.

### List sandbox containers

List all sandboxer-managed containers:

```bash
sandboxer list
```

List only running containers:

```bash
sandboxer list --running
```

### Attach to a running container

```bash
sandboxer attach <container-name-or-id>
```

### Stop a container

```bash
sandboxer stop <container-name-or-id>
```

### Remove a container

```bash
sandboxer rm <container-name-or-id>
```

### Check version

```bash
sandboxer --version
```

## Example Workflow

```bash
# Build the container image (first time only)
podman build -t sandboxer .

# Start a sandbox for your project
sandboxer run ~/projects/my-app --detach --name my-app-sandbox

# List running sandboxes
sandboxer list --running

# Attach to work in the sandbox
sandboxer attach my-app-sandbox

# Inside the container, use Claude Code
claude

# Exit and stop when done
sandboxer stop my-app-sandbox
sandboxer rm my-app-sandbox
```

## How It Works

Sandboxer uses Podman to create containers with your project folder mounted at `/home/developer/project`. The containers run as a non-root `developer` user with:

- User namespace mapping (`--userns=keep-id`) for proper file permissions
- SELinux labeling (`:Z`) for volume mounts
- Labels for tracking sandboxer-managed containers

Container names are auto-generated based on the folder path: `sandboxer-{folder-name}-{hash}`.

## License

MIT
