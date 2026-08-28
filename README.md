# Vehicle Intelligence MCP Server

Audited New Zealand vehicle intelligence server for Model Context Protocol (MCP) clients.

This server provides AI assistants and automated agents with access to audited vehicle records, reconciliation confidence scores, conflicting candidate values, monotonic revision histories, and immutable source observation audit trails.

All pipeline interactions occur over an authenticated, defensive HTTP client boundary backed by the [nz-vehicle-data-pipeline](https://github.com/sovorn/nz-vehicle-data-pipeline).

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                              MCP Clients                                │
│   (Claude Desktop, Claude Code, Codex, Custom Agent Frameworks)         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
           stdio (JSON-RPC)          │   Streamable HTTP (SSE / JSON-RPC)
                                     │   Default: http://127.0.0.1:8080/mcp
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Vehicle Intelligence MCP Server                   │
│                                                                         │
│  - Input Validation & Normalization (17-char VIN, snake_case fields)    │
│  - Tool Surface (list, lookup, explain, history, revision, obs)         │
│  - Uncertainty & Conflict Preservation (UNKNOWN != ABSENT)             │
│  - Redaction & Isolation (raw payloads confined to observation tool)    │
│  - Single-line JSON Diagnostics exclusively to stderr                   │
│  - DNS Rebinding Protection (Host & Origin allowlists)                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                             Typed Async HTTP
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     NZ Vehicle Data Pipeline API                        │
│                   (http://localhost:8000/v1)                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tool Surface

The server exposes six purpose-built MCP tools:

### 1. `list_vehicles`
Discovers canonical vehicles in the catalog via bounded pagination without loading full records or raw source evidence.
- **Inputs**:
  - `limit` (integer, optional, default: 20, range: 1–100): Bounded page size.
  - `offset` (integer, optional, default: 0, minimum: 0): Zero-based pagination offset.
- **Outputs**:
  - `items`: Bounded list of `VehicleSummary` records (`vin`, `make`, `model`, `year`, `registration_status`, `confidence_score`, `has_conflicts`, `revision_number`, `synthetic`).
  - `total`: Total count of canonical vehicles matching catalog criteria.
  - `limit`: Applied page limit.
  - `offset`: Applied page offset.
  - `disclaimer`: Synthetic notice or usage disclaimer when applicable.
- **Semantics**:
  - Empty page semantics: requesting an offset beyond available records returns `items: []` with the valid `total` count rather than an error.
  - Catalog isolation: discovery summaries omit raw source payloads and granular field provenance to protect client token budgets.

### 2. `lookup_vehicle`
Retrieves the latest canonical record for a 17-character VIN.
- **Inputs**: `vin` (string, required, normalized 17-character VIN).
- **Outputs**:
  - `canonical_fields`: Resolved vehicle attributes (`make`, `model`, `year`, `stolen_status`, `writeoff_status`, `ppsr_result`, etc.).
  - `field_provenance`: Lineage mapping each field to supporting source observations.
  - `conflicts`: Any active, unresolved disagreements between source candidates.
  - `confidence`: Calibrated score (0–100), tier band (`LOW`, `MEDIUM`, `HIGH`), and factor breakdown.
  - `synthetic_notice`: Notice when the record contains synthetic demonstration data.
- **Safety guarantee**: Never leaks internal raw payloads into canonical lookup results.

### 3. `explain_vehicle_field`
Provides an in-depth audit explanation for a specific canonical field.
- **Inputs**:
  - `vin` (string, required).
  - `field_name` (string, required, snake_case).
- **Outputs**:
  - `outcome`: Categorical outcome:
    - `RESOLVED`: Field has a clear winning canonical value.
    - `UNRESOLVED`: Conflicting candidate values exist with equal authority.
    - `ABSENT`: Field was never reported by any source for this vehicle.
  - `value`: Winning canonical value (if `RESOLVED`).
  - `conflicts`: Competing candidates and conflict rationales (if `UNRESOLVED`).
  - `field_confidence_score` & `field_components`: Freshness, authority, agreement, and validation metrics.

### 4. `get_vehicle_history`
Returns monotonic vehicle revision history in descending chronological order.
- **Inputs**:
  - `vin` (string, required).
  - `limit` (integer, optional, default 20, max 100).
  - `before_revision` (integer, optional cursor for pagination).
- **Outputs**: Array of historical revisions with material hash fingerprints.

### 5. `get_vehicle_revision`
Fetches an exact point-in-time canonical revision state.
- **Inputs**:
  - `vin` (string, required).
  - `revision_number` (integer, required, >= 1).
- **Outputs**: Full canonical revision snapshot as evaluated at that point in time.

### 6. `get_source_observation`
Retrieves the raw source record that contributed to a canonical decision.
- **Inputs**: `observation_id` (string, required).
- **Outputs**:
  - `source_system`: Originating source (e.g. `NZTA_MVR`, `NHTSA_VPIC`, `PPSR_SYNTHETIC`).
  - `retrieved_at`: Observation ingestion timestamp.
  - `raw_payload`: Complete original payload as received from the upstream source.

---

## Discovery-to-Audit Workflow

The server enables MCP clients and AI agents to systematically navigate from discovery to audit:

1. **Discover**: Call `list_vehicles(limit=20, offset=0)` to discover vehicles in the catalog and check flags like `has_conflicts` or `revision_number >= 2`.
2. **Inspect**: For an identified VIN, call `lookup_vehicle(vin=...)` to retrieve the current canonical state, confidence scores, and conflict flags.
3. **Audit Conflicts**: If `has_conflicts` is true or a specific attribute is contested, call `explain_vehicle_field(vin=..., field_name=...)` to review competing candidates.
4. **Trace Temporal Changes**: If `revision_number >= 2`, call `get_vehicle_history(vin=...)` and `get_vehicle_revision(vin=..., revision_number=...)` to inspect immutable point-in-time snapshots.
5. **Inspect Raw Evidence**: Trace `observation_id` references from field provenance to source payloads via `get_source_observation(observation_id=...)`.

---

## Getting Started

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (v0.5.26+)
- Docker and Docker Compose
- Sibling repository: `nz-vehicle-data-pipeline`

### Starting the Upstream Pipeline
The MCP server communicates with the pipeline over HTTP. Start and seed the pipeline:

```bash
cd ../nz-vehicle-data-pipeline

# Start PostgreSQL and API service
docker compose up -d --build api

# Seed deterministic demonstration vehicles
docker compose --profile tools run --rm seed
```

---

## Client Integration

### Claude Desktop (stdio)
Add the server configuration to your `claude_desktop_config.json`:

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

### Claude Code / Codex (stdio)
Run directly via CLI:

```bash
VEHICLE_MCP_PIPELINE_BASE_URL="http://localhost:8000" uv run vehicle-mcp-server
```

### Streamable HTTP (Container or Remote)
To launch the server over Streamable HTTP:

```bash
# Local development on loopback
VEHICLE_MCP_TRANSPORT="http" \
VEHICLE_MCP_HTTP_HOST="127.0.0.1" \
VEHICLE_MCP_HTTP_PORT="8080" \
VEHICLE_MCP_PIPELINE_BASE_URL="http://localhost:8000" \
uv run vehicle-mcp-server
```

Or using Docker Compose:

```bash
# Starts MCP HTTP server on 127.0.0.1:8080
PIPELINE_BASE_URL="http://host.docker.internal:8000" docker compose up -d --build
```

---

## Security & Operational Boundaries

1. **Stdio Protocol Purity**:
   - MCP over stdio requires that `stdout` is reserved strictly for JSON-RPC framing.
   - All server diagnostics and logs format as single-line JSON and write exclusively to `stderr`.
2. **Loopback & DNS Rebinding Protection**:
   - The HTTP transport enforces strict Host and Origin allowlists (`127.0.0.1`, `localhost`, `[::1]`).
   - Public binding (`0.0.0.0`) is rejected unless explicitly permitted via `VEHICLE_MCP_ALLOW_INSECURE_BIND=true` (used only in isolated container networks).
3. **No Database Direct Access**:
   - The MCP layer NEVER connects directly to the underlying PostgreSQL database. All operations flow through typed pipeline API client abstractions.
4. **Synthetic Data & Register Limitations**:
   - This server integrates with open registries (e.g. NHTSA VPIC) and calibrated synthetic demonstration registers for NZTA MVR, PPSR, and Stolen/Writeoff registries.
   - Records containing synthetic data include a prominent `synthetic_notice` disclaimer.
   - The server makes no claim of direct live access to restricted New Zealand government registers.
5. **No Silent Conflict Resolution**:
   - Missing fields are never invented. Conflicting fields are preserved as `UNRESOLVED` with competing candidates exposed for auditing.

---

## Verification & Scripts

### Automated Preflight Suite
Run all formatting, linting, strict typing, tests, and build checks locally:

```bash
bash scripts/check.sh
```

### End-to-End Demonstration Smoke Verification
To verify both stdio and Streamable HTTP transports against a live, seeded pipeline instance:

```bash
bash scripts/smoke-local.sh
```

This automated verification:
1. Bootstraps and seeds the upstream pipeline via Docker Compose.
2. Boots the MCP container over Streamable HTTP.
3. Initializes a real MCP client over stdio.
4. Exercises clean, risky, unknown, conflict, revision history, and source observation scenarios.
5. Asserts transport parity between stdio and Streamable HTTP.
6. Automatically cleans up all Docker resources upon exit.
