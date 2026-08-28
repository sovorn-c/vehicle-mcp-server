#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo " Vehicle Intelligence MCP Server — Local Preflight Verification"
echo "=================================================================="

echo "==> [1/6] Running Ruff linter..."
uv run ruff check .

echo "==> [2/6] Checking code formatting..."
uv run ruff format --check .

echo "==> [3/6] Running mypy strict type checker..."
uv run mypy src

echo "==> [4/6] Running pytest test suite..."
uv run pytest

echo "==> [5/6] Verifying package build with uv build..."
uv build

echo "==> [6/6] Verifying container build with docker build..."
docker build -t vehicle-mcp-server:local-check .

echo "=================================================================="
echo " All local preflight checks PASSED successfully!"
echo "=================================================================="
