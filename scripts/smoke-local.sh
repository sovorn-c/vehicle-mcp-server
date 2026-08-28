#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PIPELINE_DIR="${PIPELINE_DIR:-${ROOT_DIR}/../nz-vehicle-data-pipeline}"

echo "=================================================================="
echo " Starting End-to-End Local Smoke Verification"
echo "=================================================================="
echo "MCP Server Root: ${ROOT_DIR}"
echo "Pipeline Dir:    ${PIPELINE_DIR}"

if [[ ! -d "${PIPELINE_DIR}" ]]; then
    echo "ERROR: Pipeline directory not found at ${PIPELINE_DIR}"
    echo "Please set PIPELINE_DIR to the checkout of nz-vehicle-data-pipeline."
    exit 1
fi

cleanup() {
    echo "==> Cleaning up Docker Compose containers..."
    (cd "${ROOT_DIR}" && docker compose down --remove-orphans >/dev/null 2>&1 || true)
    (cd "${PIPELINE_DIR}" && docker compose down --remove-orphans >/dev/null 2>&1 || true)
}
trap cleanup EXIT INT TERM

echo "==> Starting pipeline service in ${PIPELINE_DIR}..."
(
    cd "${PIPELINE_DIR}"
    docker compose down --remove-orphans >/dev/null 2>&1 || true
    docker compose up -d --build api
)

echo "==> Waiting for Pipeline /ready endpoint..."
PIPELINE_READY=false
for i in $(seq 1 30); do
    if curl -s -f http://localhost:8000/ready >/dev/null 2>&1; then
        PIPELINE_READY=true
        break
    fi
    sleep 1
done

if [[ "${PIPELINE_READY}" != "true" ]]; then
    echo "ERROR: Pipeline /ready failed to respond within 30 seconds."
    (cd "${PIPELINE_DIR}" && docker compose logs)
    exit 1
fi

echo "==> Seeding pipeline with deterministic vehicle scenarios (Phase 1 & Phase 2)..."
(
    cd "${PIPELINE_DIR}"
    docker compose --profile tools run --rm seed
    docker compose --profile tools run --rm seed python -m nz_vehicle_data_pipeline.cli.seed --manifest fixtures/manifest.json --phase2
)

echo "==> Starting vehicle-mcp-server over Streamable HTTP..."
(
    cd "${ROOT_DIR}"
    docker compose down --remove-orphans >/dev/null 2>&1 || true
    # Point to host pipeline from container
    PIPELINE_BASE_URL="http://host.docker.internal:8000" docker compose up -d --build vehicle-mcp-server
)

echo "==> Waiting for MCP HTTP endpoint on loopback 127.0.0.1:8080..."
MCP_READY=false
for i in $(seq 1 30); do
    STATUS=$(curl --max-time 1 -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8080/mcp -H "Content-Type: application/json" -d "{}" || true)
    if [[ "${STATUS}" == "400" || "${STATUS}" == "200" || "${STATUS}" == "406" || "${STATUS}" == "421" ]]; then
        MCP_READY=true
        break
    fi
    sleep 1
done

if [[ "${MCP_READY}" != "true" ]]; then
    echo "ERROR: vehicle-mcp-server failed to bind and answer on http://127.0.0.1:8080/mcp"
    (cd "${ROOT_DIR}" && docker compose logs)
    exit 1
fi

echo "==> Executing demonstration client across stdio and Streamable HTTP..."
(
    cd "${ROOT_DIR}"
    # Use localhost:8000 for stdio subprocess
    VEHICLE_MCP_PIPELINE_BASE_URL="http://localhost:8000" uv run python -m vehicle_mcp_server.demo
)

echo "==> End-to-end smoke verification PASSED successfully!"
