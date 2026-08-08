# Transcribe Dockerfile
# Multi-stage, wheel-based build. Runtime has no pip/build tools.
# Ollama is NOT installed here — talk to a host/service endpoint.

# -----------------------------------------------------------------------------
# Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_CACHE_DIR=/root/.cache/pip

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip build \
    && python -m build \
    && pip install --no-cache-dir "$(ls dist/*.whl)[ui]"

# -----------------------------------------------------------------------------
# Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS production

ARG GIT_SHA=
ARG TRANSCRIBE_VERSION=
ARG BUILD_DATE=

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Workspace defaults (Compose overrides these with /mnt/* mounts)
ENV TRANSCRIBE_DATA_DIR=/data
ENV TRANSCRIBE_PROJECTS_DIR=/mnt/projects
ENV TRANSCRIBE_INBOX_DIR=/mnt/inbox
ENV TRANSCRIBE_EXPORT_DIR=/mnt/exports
ENV TRANSCRIBE_OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV TRANSCRIBE_HOST=0.0.0.0
ENV TRANSCRIBE_PORT=8510
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_HEADLESS=true

RUN useradd --create-home --shell /bin/bash transcribe \
    && mkdir -p /home/transcribe/.streamlit
COPY .streamlit/config.toml /home/transcribe/.streamlit/config.toml
RUN chown -R transcribe:transcribe /home/transcribe/.streamlit

USER transcribe
WORKDIR /data

LABEL org.opencontainers.image.revision="${GIT_SHA}"
LABEL org.opencontainers.image.version="${TRANSCRIBE_VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"

ENTRYPOINT ["transcribe-ui"]
