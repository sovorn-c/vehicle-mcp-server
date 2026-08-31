# Public Demo Operations Runbook

## Overview & Target Topology

This runbook documents deployment, maintenance, emergency disable, and deterministic rebuild procedures for the audited NZ Vehicle Intelligence MCP public demonstration.

The demonstration runs on the **Northflank Developer Sandbox** behind **Cloudflare**:
- **Northflank service 1:** `vehicle-pipeline` (private port 8000).
- **Northflank service 2:** `vehicle-mcp-server` (public port 8080).
- **Northflank job 1:** `db-migrate` (Alembic migration).
- **Northflank job 2:** `db-seed` (deterministic phase-2 seed).
- **Northflank addon:** `postgres-db` (private PostgreSQL 16, no public endpoint).
- **Cloudflare edge:** DNS proxy, strict TLS, Free Managed Ruleset, and 60 req/min per-IP rate-limiting on `/mcp`.

> **Non-Production Notice:** Northflank Developer Sandbox is non-production infrastructure and carries no uptime SLA or warranty. All vehicle records are synthetic.

---

## 1. Commit Pinning & Prerequisites

1. **Owner Approvals:**
   - Explicit approval for Northflank identity payment verification.
   - Cloudflare-managed domain assignment (`vehicle-intelligence.nz`).
2. **Pinned Commit References:**
   - Pipeline Ref: `ea49e71075118d6cdc3ed2426cb3620f69792cf6`
   - MCP Server Ref: Immutable release tag `v0.3.0` or exact reviewed commit SHA (never mutable branch `main`)

---

## 2. Deployment Procedure

1. **Template Application:**
   Import and execute [`deploy/northflank.template.json`](../../deploy/northflank.template.json) via the Northflank API or Dashboard.
2. **Execution Ordering:**
   - **Step A: Database Provisioning:** Ensure `postgres-db` addon is healthy.
   - **Step B: Migration (`db-migrate`):** Run `uv run alembic upgrade head` to establish the schema.
   - **Step C: Seed (`db-seed`):** Run `python -m nz_vehicle_data_pipeline.cli.seed --manifest fixtures/manifest.json --phase2` to populate deterministic fixtures.
   - **Step D: Service Readiness:** Start `vehicle-pipeline` and confirm `/ready` returns HTTP 200.
   - **Step E: MCP Exposure:** Start `vehicle-mcp-server` with `VEHICLE_MCP_ALLOWED_HOSTS` and `VEHICLE_MCP_ALLOWED_ORIGINS` matching the Cloudflare hostname and public origin.

---

## 3. Edge Configuration (Cloudflare)

Apply rules from [`deploy/cloudflare-edge.json`](../../deploy/cloudflare-edge.json):
1. **DNS:** CNAME `demo.vehicle-intelligence.nz` pointing to Northflank preview domain with Cloudflare Proxy enabled.
2. **TLS:** Strict origin SSL validation.
3. **Cache:** Bypass edge caching for `/mcp*`, `/v1/*`, `/docs*`, and `/openapi.json`.
4. **Rate Limiting:** Enforce 60 requests per 60 seconds per IP on `/mcp*`, responding with HTTP 429.

---

## 4. Health Checks & Verification

Run public smoke verification:
```bash
# Full semantic journey across all 6 tools
bash scripts/smoke-public.sh

# Security negative probes (Host, Origin, body limits)
bash scripts/smoke-public.sh --security

# Edge rate-limit verification
bash scripts/smoke-public.sh --rate-limit
```

---

## 5. Billing Review & Resource Quotas

1. Confirm all resources are mapped to Developer Sandbox (`nf-compute-10` and `nf-addon-free`).
2. Verify total resource count: exactly 2 services, 2 jobs, and 1 addon.
3. Set monthly billing alert threshold at US$1.00 to detect unexpected tier transitions.

---

## 6. Emergency Disable

If anomalous traffic or abuse is detected:
1. **Option A (Edge Cutoff):** In Cloudflare Dashboard, set DNS proxy to unproxied or toggle Under Attack mode / block rule on `/mcp*`.
2. **Option B (Origin Pause):** In Northflank Dashboard, pause `vehicle-mcp-server`.
3. **Option C (Allowlist Invalidation):** Set `VEHICLE_MCP_ALLOWED_HOSTS="disabled.local"` to reject all inbound traffic at the MCP boundary.

---

## 7. Deterministic Rebuild

Because data is entirely synthetic and reconstructable:
1. Destroy addon and services (`northflank delete project`).
2. Re-apply [`deploy/northflank.template.json`](../../deploy/northflank.template.json).
3. Re-run `db-migrate` followed by `db-seed`.
4. Run `bash scripts/smoke-public.sh` to prove full end-to-end recovery. No database backups or manual restores are necessary.
