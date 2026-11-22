# Single Dockerfile, multi-stage, shared by the devcontainer (dev target)
# and the production compose file (prod target).
#
# Base Image
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04 AS base

ARG DEBIAN_FRONTEND=noninteractive

# Install desired packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python-is-python3 \
    ffmpeg \
    libopus0 \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --break-system-packages -r requirements.txt


# ---------------------------------------------------------------------------
# Dev Image: Used by devcontainer
# ---------------------------------------------------------------------------
FROM base AS dev

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Test and lint tools (pytest, ruff), dev image only
COPY requirements-dev.txt .
RUN python -m pip install --no-cache-dir --break-system-packages -r requirements-dev.txt

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

ARG USERNAME=vscode
ARG USER_UID=1001
ARG USER_GID=$USER_UID
ENV HOME=/home/$USERNAME
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME \
    && chown -R $USERNAME:$USERNAME /app

USER $USERNAME
CMD ["sleep", "infinity"]


# ---------------------------------------------------------------------------
# prod: used by docker/docker-compose.yml. Source is copied in (immutable
# image); no dev tooling, no Node/Claude Code.
# ---------------------------------------------------------------------------
FROM base AS prod

ARG USERNAME=appuser
ARG USER_UID=1001
ARG USER_GID=$USER_UID
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

COPY --chown=$USERNAME:$USERNAME src/ ./src/

WORKDIR /app/src
USER $USERNAME
CMD ["python", "-m", "bot.main"]
