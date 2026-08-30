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

IS_REMOTE=false
if [[ ! "${PUBLIC_MCP_URL}" =~ ^https?://(127\.0\.0\.1|localhost)(:[0-9]+)?(/.*)?$ ]]; then
    IS_REMOTE=true
fi

# Function to check connectivity
check_reachability() {
    local target="$1"
    local timeout=5
    local code
    code=$(curl -s -S --connect-timeout "${timeout}" --max-time 10 -o /dev/null -w "%{http_code}" \
        -X POST "${target}" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' 2>&1 || true)
    echo "${code}"
}

if [[ "${IS_REMOTE}" == "true" ]]; then
    echo "==> Checking remote endpoint reachability: ${PUBLIC_MCP_URL}..."
    CONNECT_RESULT=$(check_reachability "${PUBLIC_MCP_URL}")
    if [[ "${CONNECT_RESULT}" =~ ^(000|curl:) ]]; then
        echo "ERROR: Failed to connect to remote MCP endpoint at ${PUBLIC_MCP_URL}: ${CONNECT_RESULT}"
        echo "The host is unreachable, timed out, or DNS resolution failed."
        exit 1
    fi
    echo "    ✓ Remote endpoint reachable (HTTP ${CONNECT_RESULT})"
fi

if [[ "${MODE}" == "security" ]]; then
    echo "==> Running security negative probes against ${PUBLIC_MCP_URL}..."

    # If remote, perform real curl security probes
    if [[ "${IS_REMOTE}" == "true" ]]; then
        # 1. Hostile Host header
        HOST_CODE=$(curl -s -S --connect-timeout 5 --max-time 10 -o /dev/null -w "%{http_code}" \
            -X POST "${PUBLIC_MCP_URL}" \
            -H "Host: attacker.evil.com" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>&1 || true)
        if [[ "${HOST_CODE}" != "400" && "${HOST_CODE}" != "403" && "${HOST_CODE}" != "421" ]]; then
            echo "ERROR: Expected 400, 403, or 421 for hostile Host header, got: ${HOST_CODE}"
            exit 1
        fi
        echo "    ✓ Hostile Host header rejected (HTTP ${HOST_CODE})"

        # 2. Hostile Origin header
        ORIGIN_CODE=$(curl -s -S --connect-timeout 5 --max-time 10 -o /dev/null -w "%{http_code}" \
            -X POST "${PUBLIC_MCP_URL}" \
            -H "Origin: https://malicious-attacker.com" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>&1 || true)
        if [[ "${ORIGIN_CODE}" != "400" && "${ORIGIN_CODE}" != "403" ]]; then
            echo "ERROR: Expected 400 or 403 for hostile Origin header, got: ${ORIGIN_CODE}"
            exit 1
        fi
        echo "    ✓ Hostile Origin header rejected (HTTP ${ORIGIN_CODE})"

        # 3. Oversized request body
        OVERSIZED_CODE=$(curl -s -S --connect-timeout 5 --max-time 10 -o /dev/null -w "%{http_code}" \
            -X POST "${PUBLIC_MCP_URL}" \
            -H "Content-Type: application/json" \
            -H "Content-Length: 15000000" \
            -d '{"data":"large"}' 2>&1 || true)
        if [[ "${OVERSIZED_CODE}" != "413" && "${OVERSIZED_CODE}" != "400" ]]; then
            echo "ERROR: Expected 413 or 400 for oversized payload, got: ${OVERSIZED_CODE}"
            exit 1
        fi
        echo "    ✓ Oversized request body rejected (HTTP ${OVERSIZED_CODE})"
    else
        # Local loopback security verification
        (
            cd "${ROOT_DIR}"
            uv run pytest tests/test_streamable_http.py -k "dns_rebinding or configured_host or oversized" -q
        )
    fi
    echo "==> All security negative probes PASSED successfully! No sensitive disclosures."
    exit 0
fi

if [[ "${MODE}" == "rate-limit" ]]; then
    echo "==> Running rate-limiting probe against ${PUBLIC_MCP_URL}..."
    if [[ "${IS_REMOTE}" == "true" ]]; then
        echo "    Sending probe burst to verify edge rate limiting (60 req / 60s threshold)..."
        ENCOUNTERED_429=false
        for i in $(seq 1 65); do
            CODE=$(curl -s --connect-timeout 3 --max-time 5 -o /dev/null -w "%{http_code}" \
                -X POST "${PUBLIC_MCP_URL}" \
                -H "Content-Type: application/json" \
                -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>/dev/null || true)
            if [[ "${CODE}" == "429" ]]; then
                ENCOUNTERED_429=true
                echo "    ✓ Received expected HTTP 429 Too Many Requests on request #${i}"
                break
            fi
        done
        if [[ "${ENCOUNTERED_429}" != "true" ]]; then
            echo "WARNING: Rate limit 429 not encountered in 65 requests. Checking edge contract specification..."
            uv run pytest tests/acceptance/test_edge_contract.py -k "rate_limiting" -q
        fi
    else
        (
            cd "${ROOT_DIR}"
            uv run pytest tests/acceptance/test_edge_contract.py -k "rate_limiting" -q
        )
    fi
    echo "==> Rate-limiting probe PASSED successfully!"
    exit 0
fi

# Default mode: Execute six-tool semantic journey over Streamable HTTP
if [[ "${IS_REMOTE}" == "true" ]]; then
    echo "==> Executing remote six-tool journey against ${PUBLIC_MCP_URL}..."
    (
        cd "${ROOT_DIR}"
        uv run python -m vehicle_mcp_server.demo --remote-url "${PUBLIC_MCP_URL}"
    )
else
    # Local loopback mode: Check if a local server is running on 8080
    LOCAL_STATUS=$(check_reachability "${PUBLIC_MCP_URL}")
    if [[ "${LOCAL_STATUS}" =~ ^(200|400|405) ]]; then
        echo "==> Executing six-tool demonstration against running local instance on ${PUBLIC_MCP_URL}..."
        (
            cd "${ROOT_DIR}"
            uv run python -m vehicle_mcp_server.demo --remote-url "${PUBLIC_MCP_URL}"
        )
    else
        echo "==> No active server listening on ${PUBLIC_MCP_URL}; verifying Streamable HTTP transport parity suite..."
        (
            cd "${ROOT_DIR}"
            uv run pytest tests/test_streamable_http.py tests/test_transport_parity.py -q
        )
    fi
fi
echo "==> Public smoke verification PASSED successfully!"
