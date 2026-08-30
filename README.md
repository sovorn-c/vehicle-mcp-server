# Vehicle Intelligence MCP Server

[![CI](https://github.com/sovorn-c/vehicle-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/sovorn-c/vehicle-mcp-server/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-stdio%20%7C%20Streamable%20HTTP-5A67D8)

> A read-only MCP server for evidence-preserving access to audited New Zealand vehicle records.

A canonical value is not enough when the underlying sources disagree. This server gives MCP clients the value, provenance, confidence, conflicts, revision history, and source observations needed to inspect the result.

The server is a typed integration layer over the [NZ Vehicle Data Pipeline](https://github.com/sovorn-c/nz-vehicle-data-pipeline). The pipeline owns vehicle evidence and reconciliation. This project exposes that evidence through six focused MCP tools without duplicating the pipeline's decision logic.

## What the server provides

- **Evidence with every result:** Canonical fields retain provenance, confidence, conflict state, and synthetic-data notices.
- **Explicit uncertainty:** `UNKNOWN`, `UNRESOLVED`, and absent values remain distinct.
- **Point-in-time audit:** Clients can inspect monotonic history and retrieve an exact immutable revision.
- **Controlled source access:** Raw payloads appear only through an explicit source-observation lookup.
- **Transport parity:** The same tool catalog and behavior are available over stdio and Streamable HTTP.
- **Defensive boundaries:** Strict schemas, bounded responses, timeouts, retries, safe errors, and loopback-first HTTP defaults protect each trust boundary.

## Architecture

```text
MCP client
   │
   ├── stdio
   └── Streamable HTTP  http://127.0.0.1:8080/mcp
   │
   ▼
Vehicle Intelligence MCP Server
   ├── strict tool-input validation
   ├── evidence-preserving result projection
   ├── stable error translation
   └── typed asynchronous pipeline client
   │
   ▼  HTTP /v1
NZ Vehicle Data Pipeline API
   ├── canonical records
   ├── reconciliation and confidence
   ├── immutable revisions
   └── source observations
```

The MCP server has no database and no application cache. All vehicle-data reads pass through one typed asynchronous HTTP client.

## Quick start

### Prerequisites

- Git
- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.5.26 or later
- Docker with Docker Compose
- `curl`

### Run the verified demonstration

The smoke script starts both services, seeds deterministic scenarios, exercises both MCP transports, and removes its containers when complete.

```bash
mkdir vehicle-intelligence-demo
cd vehicle-intelligence-demo

git clone https://github.com/sovorn-c/nz-vehicle-data-pipeline.git
git -C nz-vehicle-data-pipeline checkout 21024499ec71bc09b33b136de9ca369ca052685b

git clone https://github.com/sovorn-c/vehicle-mcp-server.git
cd vehicle-mcp-server
uv sync --frozen

PIPELINE_DIR="../nz-vehicle-data-pipeline" bash scripts/smoke-local.sh
```

A successful run demonstrates:

- catalog discovery from five seeded vehicles
- clean, risky, unknown, and conflicting evidence states
- immutable revision history
- exact source-observation retrieval
- identical stdio and Streamable HTTP outcomes

## Run the server

The upstream pipeline API must be available before the MCP server starts. Its default address is `http://localhost:8000`.

### stdio

```bash
VEHICLE_MCP_PIPELINE_BASE_URL="http://localhost:8000" \
uv run vehicle-mcp-server
```

Standard output is reserved for MCP protocol messages. Server diagnostics use standard error.

### Streamable HTTP

```bash
VEHICLE_MCP_TRANSPORT="http" \
VEHICLE_MCP_HTTP_HOST="127.0.0.1" \
VEHICLE_MCP_HTTP_PORT="8080" \
VEHICLE_MCP_PIPELINE_BASE_URL="http://localhost:8000" \
uv run vehicle-mcp-server
```

The MCP endpoint is `http://127.0.0.1:8080/mcp`.

### Docker Compose

```bash
PIPELINE_BASE_URL="http://host.docker.internal:8000" \
docker compose up -d --build
```

Docker Compose publishes the MCP endpoint on loopback at `127.0.0.1:8080`.

## Connect an MCP client

The server is model- and client-agnostic. Any MCP client that supports stdio or Streamable HTTP can use the same six tools.

### OpenAI Codex

Register the stdio server with the Codex CLI. Replace `/path/to/vehicle-mcp-server` with the local repository path.

```bash
codex mcp add vehicle-intelligence \
  --env VEHICLE_MCP_TRANSPORT=stdio \
  --env VEHICLE_MCP_PIPELINE_BASE_URL=http://localhost:8000 \
  -- uv run --directory /path/to/vehicle-mcp-server vehicle-mcp-server
```

Verify the shared Codex CLI and IDE-extension configuration:

```bash
codex mcp list
```

See the official [Codex MCP configuration guide](https://developers.openai.com/codex/mcp) for UI and `config.toml` alternatives.

### Claude Desktop

Add this entry to `claude_desktop_config.json`. Replace `/path/to/vehicle-mcp-server` with the local repository path.

```json
{
  "mcpServers": {
    "vehicle-intelligence": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/vehicle-mcp-server",
        "vehicle-mcp-server"
      ],
      "env": {
        "VEHICLE_MCP_TRANSPORT": "stdio",
        "VEHICLE_MCP_PIPELINE_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Other MCP clients

Use these connection values in clients that provide their own MCP configuration interface:

| Transport | Connection |
|---|---|
| stdio | Command: `uv`; arguments: `run --directory /path/to/vehicle-mcp-server vehicle-mcp-server`; set the two environment variables shown above. |
| Streamable HTTP | URL: `http://127.0.0.1:8080/mcp`; start the server in HTTP mode first. |

## Tool catalog

| Tool | Main input | Purpose |
|---|---|---|
| `list_vehicles` | `limit`, `offset` | Return one bounded page of canonical vehicle summaries for discovery. |
| `lookup_vehicle` | `vin` | Return the current canonical record with provenance, conflicts, confidence, and revision metadata. |
| `explain_vehicle_field` | `vin`, `field_name` | Explain whether one field is `RESOLVED`, `UNRESOLVED`, or `ABSENT`. |
| `get_vehicle_history` | `vin`, pagination | Return bounded revision history in newest-first order. |
| `get_vehicle_revision` | `vin`, `revision_number` | Return one exact immutable canonical revision. |
| `get_source_observation` | `observation_id` | Return one exact source observation and its verified raw payload. |

Catalog pagination accepts `limit` values from 1 through 100 and an `offset` of zero or more. An offset beyond the catalog returns an empty page, not an error.

## Discovery-to-audit workflow

1. Call `list_vehicles` to discover available records and identify conflicts or later revisions.
2. Call `lookup_vehicle` to inspect the current canonical state and its audit metadata.
3. Call `explain_vehicle_field` to inspect a resolved, unresolved, or absent field.
4. Call `get_vehicle_history` and `get_vehicle_revision` to compare point-in-time states.
5. Call `get_source_observation` with a provenance identifier to inspect the original evidence.

This workflow moves from a bounded summary to raw evidence without placing full payloads in every result.

## Engineering decisions

| Decision | Reason |
|---|---|
| Keep reconciliation in the pipeline | One system owns candidate selection, confidence, conflicts, and revision publication. |
| Use one typed pipeline client | All upstream reads share validation, timeout, retry, response-size, and error rules. |
| Validate both inputs and responses | The MCP boundary rejects invalid calls and fails closed on upstream contract drift. |
| Preserve uncertain states | The integration layer does not turn incomplete evidence into a definitive claim. |
| Keep tools transport-independent | stdio and Streamable HTTP expose the same schemas and behavior. |
| Avoid local persistence | The server cannot return a silent stale fallback when the pipeline is unavailable. |

## Security and limitations

- The server never connects directly to the pipeline database.
- VINs, observation identifiers, tool arguments, and pipeline responses are treated as untrusted input.
- Pipeline responses have a configurable size ceiling. Transient idempotent reads use bounded retries.
- Raw exceptions, stack traces, credentials, and upstream payload values do not enter public errors or diagnostics.
- Streamable HTTP enables DNS-rebinding protection with loopback Host and Origin allowlists.
- Non-loopback binding requires the explicit `VEHICLE_MCP_ALLOW_INSECURE_BIND=true` override.
- Raw source payloads are available only through `get_source_observation`.
- Synthetic records retain a visible `synthetic_notice`.
- The project does not claim live access to NZTA, PPSR, Police, insurer, or other restricted registers.
- The current HTTP mode is for local or private use. Add authentication, authorization, and rate limiting before public deployment.

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `VEHICLE_MCP_PIPELINE_BASE_URL` | `http://localhost:8000` | Pipeline API base URL. `PIPELINE_BASE_URL` is also accepted. |
| `VEHICLE_MCP_TRANSPORT` | `stdio` | Select `stdio` or `http`. |
| `VEHICLE_MCP_HTTP_HOST` | `127.0.0.1` | Streamable HTTP bind host. |
| `VEHICLE_MCP_HTTP_PORT` | `8080` | Streamable HTTP bind port. |
| `VEHICLE_MCP_ALLOW_INSECURE_BIND` | `false` | Permit a non-loopback bind for a controlled container network. |
| `VEHICLE_MCP_CONNECT_TIMEOUT` | `2.0` | Pipeline connection timeout in seconds. |
| `VEHICLE_MCP_POOL_TIMEOUT` | `2.0` | Connection-pool timeout in seconds. |
| `VEHICLE_MCP_READ_TIMEOUT` | `10.0` | Pipeline read timeout in seconds. |
| `VEHICLE_MCP_WRITE_TIMEOUT` | `5.0` | Pipeline write timeout in seconds. |
| `VEHICLE_MCP_MAX_ATTEMPTS` | `3` | Maximum attempts for transient reads. Valid range: 1 through 5. |
| `VEHICLE_MCP_MAX_RESPONSE_BYTES` | `1048576` | Maximum pipeline response size. Valid range: 10 KiB through 10 MiB. |

## Project layout

```text
src/vehicle_mcp_server/
├── client.py       # typed asynchronous pipeline boundary
├── config.py       # immutable environment configuration
├── models.py       # strict tool and upstream contracts
├── server.py       # MCP catalog and transport application
└── tools.py        # tool behavior and safe error translation

tests/
├── acceptance/     # public documentation and delivery contracts
├── integration/    # live pipeline contract checks
└── test_*.py       # unit, transport, security, and parity tests
```

## Verification

Run the complete local preflight:

```bash
bash scripts/check.sh
```

The preflight runs Ruff, formatting checks, strict mypy, pytest, a package build, and a Docker build.

Run the cross-repository behavior check:

```bash
PIPELINE_DIR="../nz-vehicle-data-pipeline" bash scripts/smoke-local.sh
```

The CI workflow repeats the preflight stages and runs the smoke check against the pinned compatible pipeline revision.

## Project status

Release `0.2.0` provides six read-only tools over stdio and Streamable HTTP. The current release targets local and private integrations with deterministic demonstration data.
