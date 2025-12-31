FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ─────────────────────────────────────────────────────────────────────────────
# System dependencies
# ─────────────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    git \
    curl \
    procps \
    sudo \
    libpq-dev \
    sqlite3 \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────────────────────
# Non-root user
# ─────────────────────────────────────────────────────────────────────────────
RUN useradd -m -g users vscode \
    && echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/vscode \
    && chmod 0440 /etc/sudoers.d/vscode

# ─────────────────────────────────────────────────────────────────────────────
# Python environment
# ─────────────────────────────────────────────────────────────────────────────
WORKDIR /workspace
USER vscode

# Create venv in home directory
RUN python -m venv /home/vscode/.venv \
    && . /home/vscode/.venv/bin/activate \
    && pip install --upgrade pip

ENV PATH="/home/vscode/.venv/bin:$PATH" \
    PYTHONPATH="${PYTHONPATH}:/workspace/src"
