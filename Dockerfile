# Multi-architecture development container with uv, bun, golang, claude-code, and opencode
# Supports amd64 and arm64 architectures

FROM ubuntu:24.04

# Build arguments
ARG TARGETARCH
ARG GO_VERSION=1.23.5

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies in a single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    unzip \
    ripgrep \
    jq \
    sudo \
    neovim \
    tmux \
    podman \
    fuse-overlayfs \
    uidmap \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with passwordless sudo
# Handle case where UID/GID 1000 may already exist (common in Ubuntu)
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupdel ubuntu 2>/dev/null || true \
    && groupadd --gid 1000 developer \
    && useradd --uid 1000 --gid 1000 -m developer \
    && echo "developer ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && mkdir -p /home/developer/.local/bin \
    && chown -R developer:developer /home/developer

# Configure subuid/subgid mappings for rootless nested Podman
RUN echo "developer:100000:65536" >> /etc/subuid \
    && echo "developer:100000:65536" >> /etc/subgid

# Create XDG_RUNTIME_DIR for rootless Podman (normally created by systemd at login)
RUN mkdir -p /run/user/1000 \
    && chown developer:developer /run/user/1000 \
    && chmod 700 /run/user/1000

# Install Go (architecture-aware)
RUN case "${TARGETARCH}" in \
        amd64) GOARCH="amd64" ;; \
        arm64) GOARCH="arm64" ;; \
        *) GOARCH="amd64" ;; \
    esac \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GOARCH}.tar.gz" | tar -C /usr/local -xz

# Switch to non-root user
USER developer
WORKDIR /home/developer

# Set up PATH and Go environment
ENV PATH="/home/developer/.local/bin:/home/developer/.bun/bin:/home/developer/.cargo/bin:/home/developer/go/bin:/usr/local/go/bin:${PATH}"
ENV GOPATH="/home/developer/go"
ENV XDG_RUNTIME_DIR="/run/user/1000"

# Create Go directories
RUN mkdir -p "${GOPATH}/src" "${GOPATH}/bin" "${GOPATH}/pkg"

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pyright (Python type checker)
RUN uv tool install pyright

# Install bun (JavaScript runtime)
RUN curl -fsSL https://bun.sh/install | bash

# Install Claude Code
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install OpenCode (longer timeout as it compiles from source)
RUN curl -fsSL --connect-timeout 60 --max-time 300 https://opencode.ai/install | bash

# Update bashrc with PATH for interactive shells
RUN echo 'export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$HOME/.bun/bin:$HOME/.cargo/bin:$HOME/go/bin:/usr/local/go/bin:$PATH"' >> ~/.bashrc

# Create project mount point and config directories
RUN mkdir -p /home/developer/project \
    /home/developer/.config \
    /home/developer/.cache

# Configure Podman for nested container operation (Podman-in-Podman)
RUN mkdir -p /home/developer/.config/containers

RUN printf '[storage]\n\
driver = "overlay"\n\
runroot = "/run/user/1000/containers"\n\
graphroot = "/home/developer/.local/share/containers/storage"\n\
\n\
[storage.options.overlay]\n\
mount_program = "/usr/bin/fuse-overlayfs"\n' > /home/developer/.config/containers/storage.conf

RUN printf '[containers]\n\
netns = "host"\n\
userns = "host"\n\
ipcns = "host"\n\
utsns = "host"\n\
cgroupns = "host"\n\
cgroups = "disabled"\n\
log_driver = "k8s-file"\n\
default_sysctls = []\n\
\n\
[engine]\n\
cgroup_manager = "cgroupfs"\n\
events_logger = "file"\n' > /home/developer/.config/containers/containers.conf

# Set working directory to project mount point
WORKDIR /home/developer/project

# Default command
CMD ["bash"]
