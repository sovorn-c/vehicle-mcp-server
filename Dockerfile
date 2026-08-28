# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.5.26-python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies using lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and build/install project
COPY src/ src/
COPY README.md README.md
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Run as non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    VEHICLE_MCP_TRANSPORT=http \
    VEHICLE_MCP_HTTP_HOST=0.0.0.0 \
    VEHICLE_MCP_HTTP_PORT=8080 \
    VEHICLE_MCP_ALLOW_INSECURE_BIND=true

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import socket; s = socket.create_connection(('127.0.0.1', 8080), timeout=2); s.close()" || exit 1

ENTRYPOINT ["vehicle-mcp-server"]
