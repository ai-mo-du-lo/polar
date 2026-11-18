# FixBugs "Local, container" image for the Polar demo workspace (D135).
# FixBugs builds it from <workspace>/.devcontainer and runs each command in it.
# The first two steps copy dev/docker/Dockerfile.api.dev byte for byte, so
# Docker reuses the demo stack's cached layers.
FROM python:3.14.6-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    fonts-noto-cjk \
    libpq-dev \
    curl \
    postgresql-client \
    && sed -i -e 's|^mozilla/emSign_ECC_Root_CA_-_G3.crt|!&|' \
      -e 's|^mozilla/Comodo_AAA_Services_root.crt|!&|' /etc/ca-certificates.conf \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager (pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

# Polar's tests need Postgres on 127.0.0.1:5432 and S3 on 127.0.0.1:9000
# (server/.env.testing); Redis is faked. The entrypoint starts throwaway
# servers per command. MinIO is the demo stack's own image, already local.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql \
    && rm -rf /var/lib/apt/lists/*
COPY --from=bitnamilegacy/minio:2024.5.28 /opt/bitnami/minio/bin/minio /usr/local/bin/minio

# FixBugs runs commands as uid 1000 on Windows; Postgres needs a passwd entry.
RUN useradd --uid 1000 --no-create-home --home-dir /home/sandbox sandbox
# The bind-mounted workspace is not owned by uid 1000; git would refuse it.
RUN git config --system --add safe.directory '*'

# Polar's dependencies, baked in once: FixBugs copies the workspace for each
# validation attempt without .venv, so a workspace venv would re-sync each time.
# The demo setup copies server/pyproject.toml, uv.lock and .python-version here.
ENV UV_PROJECT_ENVIRONMENT=/opt/polar-venv \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/polar-venv \
    PATH=/opt/polar-venv/bin:$PATH
COPY pyproject.toml uv.lock .python-version /opt/polar/
RUN mkdir /opt/polar-venv && chown 1000:1000 /opt/polar-venv
USER 1000
RUN cd /opt/polar && uv sync --frozen --no-install-project && rm -rf /tmp/uv-cache
USER root

# Polar's settings require the email renderer binary (built with Node). Its own
# CI uses an empty placeholder where emails are not rendered; so does the demo.
ENV POLAR_EMAIL_RENDERER_BINARY_PATH=/opt/polar/email-renderer
RUN touch /opt/polar/email-renderer

COPY entrypoint.sh /usr/local/bin/fixbugs-demo-entrypoint
RUN chmod 0755 /usr/local/bin/fixbugs-demo-entrypoint

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/local/bin/fixbugs-demo-entrypoint"]
