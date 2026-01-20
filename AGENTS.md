# Sandboxer

THIS PROJECT USES uv and you always need to use uv when trying to run python

A CLI tool for sandboxing folders into containers with Claude Code support.

## Project Overview

This project provides:

1. **Dockerfile** - Builds an Ubuntu-based image pre-configured with:
   - [uv](https://github.com/astral-sh/uv) - Fast Python package manager
   - [Claude Code](https://claude.ai/claude-code) - Anthropic's CLI for Claude

2. **CLI** - A Python command-line tool that:
   - Takes a folder path and container image as input
   - Mounts the folder into a containerized environment
   - Uses Podman for container orchestration

## Tech Stack

- **Container Runtime**: Podman
- **Python Tooling**: uv
- **CLI Framework**: TBD (likely Click or Typer)

## Development

Install dependencies:
```bash
./install.sh
```

This installs Podman, uv, and Claude Code.

## Usage

```bash
# Example (planned CLI interface)
sandboxer <folder-path> --image <image-name>
```
