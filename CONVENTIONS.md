# Conventions

## Conventional Commits and versioning

All commits MUST follow Conventional Commits 1.0.0.
Releases MUST follow Semantic Versioning 2.0.0.
Use `<type>(<scope>): <description>` for every commit subject.
Use `feat` for features and `fix` for defects.
Use `BREAKING CHANGE:` or `!` for incompatible changes.
NEVER add AI attribution footers.

## Git workflow

Use feature branches for production work.
Keep `main` green and releasable.
Use `solo-git` workflow mode from `specs/state.yaml`.
Run Preflight before integration.
Check remote CI with `gh pr checks` when a pull request exists.
NEVER push directly to protected branches.
NEVER run destructive Git commands without explicit user approval.

## Agent workflow

Read `AGENTS.md` and `specs/` before changing code.
Route product work through bigpowers skills.
Write approved scope before implementation tasks.
Write runnable verification commands into every implementation plan.
Use TDD for non-trivial behavior and defect fixes.
Keep planning output under `specs/`.

## Always Green and Shift Left

Preflight defines the complete local verification stack.
Preflight MUST pass before implementation, verification, or integration advances.
CI MUST pass before integration when remote CI applies.
A reproducible gate failure blocks forward work.
Fix failures while feedback remains cheap.

### Preflight

Run this command after the Python package scaffold exists:

```bash
uv run ruff check . \
  && uv run ruff format --check . \
  && uv run mypy src \
  && uv run pytest \
  && uv build
```

## Discovered defects

Treat every reproducible gate failure as a defect.
Use this mandatory fix-or-log ladder:

1. Use `quick-fix` for eligible data-only changes.
2. Use `fix-bug` when logic or investigation is required.
3. Log a bug only when reproduction remains blocked.

Keep discovered fixes in separate Conventional Commits.
Do NOT continue while Preflight or CI remains red.

### Banned failure dismissals

| Do not say | Required action |
|---|---|
| Pre-existing issue | Reproduce, fix, or log the defect. |
| Unrelated to this session | Reproduce, fix, or log the defect. |
| Not introduced by this change | Prove with isolation, then fix or log. |
| Out of scope | Stop forward work and apply the ladder. |

## Planning cockpit

All planning output MUST live under `specs/`.
`specs/state.yaml` owns active workflow state and handoff signals.
`specs/release-plan.yaml` owns epic ordering and release intent.
`specs/execution-status.yaml` owns story and epic status.
`specs/product/` owns vision, scope, and glossary artifacts.
`specs/epics/` owns story requirements and implementation tasks.
`specs/tech-architecture/` owns architecture and quality plans.
`specs/verifications/` owns verification evidence.
`specs/bugs/` owns defect investigations and registry data.
Do NOT duplicate status across cockpit files.

## Architecture

Treat the NZ Vehicle Data Pipeline as the vehicle-data system of record.
Access pipeline capabilities through its versioned HTTP API.
Route all upstream calls through one typed async `VehiclePipelineClient`.
Use `httpx2.AsyncClient` through the server lifespan; do not add legacy `httpx`.
Keep MCP tool handlers independent from HTTP implementation details.
Keep transport configuration independent from tool behavior.
Do NOT connect directly to the pipeline database.
Do NOT duplicate pipeline reconciliation or confidence logic.
Use interfaces only when multiple implementations exist.
Do NOT add abstractions for future needs.

## Python style

Target Python 3.12.
Use a `src/vehicle_mcp_server/` package layout.
Use explicit types on public functions.
Use strict Pydantic models at trust boundaries.
Reject unknown fields in input and upstream response models.
Use early returns instead of nested control flow.
Keep functions focused and modules cohesive.
Prefer standard library features before dependencies.
Delete dead code instead of commenting it out.
Use Ruff for formatting and lint rules.
Use mypy strict mode.

## MCP contracts

Use the official MCP Python SDK.
Expose stdio and Streamable HTTP transports.
Reserve stdio `stdout` exclusively for MCP protocol messages.
Design tools around agent tasks, not raw REST endpoint names.
Give every tool a precise description and strict schema.
Return structured content with stable field names.
Preserve provenance, conflicts, confidence, and synthetic notices.
Keep tool results concise without hiding audit evidence.
NEVER implement MCP protocol framing manually.
NEVER expose tools unsupported by the pipeline API.

## Pipeline API integrity

Treat every pipeline response as untrusted boundary data.
Validate upstream responses before returning MCP results.
Preserve `UNKNOWN`, `UNRESOLVED`, and missing values exactly.
NEVER convert uncertain evidence into definitive claims.
NEVER fabricate data when the pipeline is unavailable.
NEVER silently cache stale vehicle answers.
Keep the upstream base URL configurable.
Do NOT hard-code credentials or deployment addresses.

## API and error contracts

Validate every tool input before upstream access.
Map pipeline failures into stable MCP error categories.
Give errors actionable remediation guidance.
Retry only transient failures from idempotent reads.
Do NOT retry validation failures or missing records.
Do NOT expose raw exceptions or internal stack traces.
Do NOT include secrets in error messages.

## Security and privacy

Treat VINs and observation identifiers as untrusted input.
Validate all identifiers before building request paths.
Use encoded path parameters through the HTTP client.
Redact authorization headers and credentials from logs.
NEVER claim access to restricted NZ vehicle registers.
NEVER store real personal vehicle-owner information.
NEVER present synthetic evidence as official data.
NEVER modify the upstream pipeline without separate approval.

## Tests

Tests MUST be Fast, Independent, Repeatable, Self-Validating, and Timely.
Test behavior through public interfaces.
Add one focused test for every non-trivial branch.
Add a regression test for every defect fix.
Cover empty, minimum, maximum, malformed, and timeout inputs.
Keep unit tests offline and deterministic.
Use fake pipeline clients for tool unit tests.
Use HTTP contract tests for pipeline response validation.
Use integration tests against the Dockerized pipeline.
Test both stdio and Streamable HTTP behavior.
Verify that stdio emits no diagnostic output.
Do NOT skip tests without a documented unresolved ambiguity.

## Logging

Send all stdio diagnostics to `stderr`.
Use structured logs for Streamable HTTP deployments.
Include operation and correlation identifiers when available.
Redact secrets and sensitive upstream payloads.
Do NOT log authorization headers or complete raw observations.

## Defensive code

Implement these approved categories:

- Apply explicit connect and response timeouts.
- Retry transient idempotent reads with bounded exponential backoff.
- Return structured unavailable errors when the pipeline fails.
- Preserve uncertainty instead of degrading to invented answers.

Do NOT add a circuit breaker before failure volume justifies it.
Do NOT rate-limit local stdio usage.
Add rate limiting before exposing a public HTTP deployment.
