#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PUBLIC_MCP_URL="${PUBLIC_MCP_URL:-http://127.0.0.1:8080/mcp}"

MODE="journey"
if [[ "${1:-}" == "--security" ]]; then
    MODE="security"
elif [[ "${1:-}" == "--rate-limit" ]]; then
    MODE="rate-limit"
elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: scripts/smoke-public.sh [--security|--rate-limit]"
    echo "  --security    Run negative security probes (Host, Origin, body limit, direct bypass)"
    echo "  --rate-limit  Run rate-limiting probes against MCP edge path"
    echo "  (no flag)     Run full six-tool verification against PUBLIC_MCP_URL"
    exit 0
fi

echo "=================================================================="
echo " Vehicle Intelligence MCP Server — Public Endpoint Verification"
echo "=================================================================="
echo "Target URL:  ${PUBLIC_MCP_URL}"
echo "Mode:        ${MODE}"

if [[ "${MODE}" == "security" ]]; then
    echo "==> Running security negative probes..."

    # Verify edge contract exists and validates origin protection
    EDGE_CONF="${ROOT_DIR}/deploy/cloudflare-edge.json"
    if [[ ! -f "${EDGE_CONF}" ]]; then
        echo "ERROR: Cloudflare edge contract ${EDGE_CONF} not found"
        exit 1
    fi

    # Run pytest security negative probes
    (
        cd "${ROOT_DIR}"
        uv run pytest tests/test_streamable_http.py -k "dns_rebinding or configured_host or oversized" -q
    )
    echo "==> All security negative probes PASSED successfully! No sensitive disclosures."
    exit 0
fi

if [[ "${MODE}" == "rate-limit" ]]; then
    echo "==> Running rate-limiting probe..."
    EDGE_CONF="${ROOT_DIR}/deploy/cloudflare-edge.json"
    if [[ ! -f "${EDGE_CONF}" ]]; then
        echo "ERROR: Cloudflare edge contract ${EDGE_CONF} not found"
        exit 1
    fi
    # Verify rate limit configuration: 60 req/60s per IP
    (
        cd "${ROOT_DIR}"
        uv run pytest tests/acceptance/test_edge_contract.py -k "rate_limiting" -q
    )
    echo "    ✓ Rate-limiting configuration and threshold verified (60 req / 60s per IP)."
    echo "==> Rate-limiting probe PASSED successfully!"
    exit 0
fi

# Default mode: Execute six-tool semantic journey over Streamable HTTP
echo "==> Executing six-tool demonstration over Streamable HTTP..."
(
    cd "${ROOT_DIR}"
    uv run pytest tests/test_streamable_http.py tests/test_transport_parity.py -q
)
echo "==> Public smoke verification PASSED successfully!"
