"""Automated demonstration client exercising all six vehicle intelligence tools."""

import asyncio
import json
from typing import Any

import httpx2
from mcp.client import Client
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.server import create_server


def _extract_tool_payload(result: Any) -> Any:
    """Extract and parse structured payload from a CallToolResult."""
    if hasattr(result, "structured_content") and result.structured_content is not None:
        sc = result.structured_content
        if isinstance(sc, dict) and "result" in sc and len(sc) == 1:
            return sc["result"]
        return sc
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "text") and item.text:
                try:
                    parsed = json.loads(item.text)
                    if isinstance(parsed, dict) and "result" in parsed and len(parsed) == 1:
                        return parsed["result"]
                    return parsed
                except Exception:
                    continue
    return None


async def run_demonstration(
    pipeline_base_url: str = "http://localhost:8000",
    http_url: str = "http://127.0.0.1:8080/mcp",
    stdio_server: Any = None,
) -> None:
    """Execute end-to-end demonstration exercising all six vehicle intelligence tools."""
    print("==================================================================")
    print(" Vehicle Intelligence MCP Server — End-to-End Demonstration")
    print("==================================================================")

    # Resolve stdio server
    resolved_server = stdio_server or create_server(
        ServerConfig(pipeline_base_url=pipeline_base_url)
    )

    print("\n[1/8] Initializing stdio transport and verifying tool catalog...")
    async with Client(resolved_server) as stdio_client:
        stdio_tools_res = await stdio_client.list_tools()
        stdio_tool_names = sorted([t.name for t in stdio_tools_res.tools])
        print(f"      Stdio tools ({len(stdio_tool_names)}): {', '.join(stdio_tool_names)}")
        assert len(stdio_tool_names) == 6, f"Expected 6 tools, got {len(stdio_tool_names)}"

        # Step 2: Catalog Discovery
        print("\n[2/8] Discovering Canonical Vehicles in Catalog...")
        cat_res = await stdio_client.call_tool(
            "list_vehicles",
            arguments={"limit": 20, "offset": 0},
        )
        catalog = _extract_tool_payload(cat_res)
        assert isinstance(catalog, dict)
        assert "items" in catalog
        assert catalog.get("total") == 5, (
            f"Expected total 5 canonical vehicles, got {catalog.get('total')}"
        )
        assert len(catalog["items"]) == 5, (
            f"Expected 5 items in catalog, got {len(catalog['items'])}"
        )
        print(
            f"      Discovered {len(catalog['items'])} vehicles "
            f"(total in catalog: {catalog.get('total', len(catalog['items']))})"
        )

        # Dynamic selection of conflict vehicle
        conflict_candidates = [
            item["vin"] for item in catalog["items"] if item.get("has_conflicts") is True
        ]
        assert conflict_candidates, (
            "Catalog must contain at least one vehicle with has_conflicts=True"
        )
        conflict_vin = conflict_candidates[0]
        print(f"      Selected conflict vehicle from catalog: {conflict_vin}")

        # Dynamic selection of multi-revision temporal vehicle
        temporal_candidates = [
            item["vin"] for item in catalog["items"] if item.get("revision_number", 1) >= 2
        ]
        assert temporal_candidates, (
            "Catalog must contain at least one vehicle with revision_number >= 2"
        )
        temporal_vin = temporal_candidates[0]
        print(f"      Selected temporal vehicle from catalog: {temporal_vin}")

        # Scenario 1: Clean Vehicle
        print("\n[3/8] Scenario 1: Clean Vehicle (1HGCR2F85HA000000)")
        res = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": "1HGCR2F85HA000000"},
        )
        data = _extract_tool_payload(res)
        assert data["canonical_fields"]["make"] == "HONDA"
        assert data["canonical_fields"]["stolen_status"] == "NOT_LISTED"
        assert data.get("synthetic_notice") is not None
        assert "raw_payload" not in str(data), "raw_payload must never leak in canonical lookup!"
        make = data["canonical_fields"]["make"]
        stolen = data["canonical_fields"]["stolen_status"]
        print(f"      Make: {make}, Stolen: {stolen}")
        print(f"      Synthetic notice preserved: {bool(data.get('synthetic_notice'))}")

        # Explain stolen_status on clean vehicle
        exp_res = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": "1HGCR2F85HA000000", "field_name": "stolen_status"},
        )
        exp_data = _extract_tool_payload(exp_res)
        assert exp_data["outcome"] == "RESOLVED"
        assert exp_data["value"] == "NOT_LISTED"
        print(f"      Explanation outcome: {exp_data['outcome']} ({exp_data['value']})")

        # Scenario 2: Risky Vehicle
        print("\n[4/8] Scenario 2: Risky Vehicle (1FA6P8CF8H5000000)")
        res_risky = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": "1FA6P8CF8H5000000"},
        )
        risky_data = _extract_tool_payload(res_risky)
        assert risky_data["canonical_fields"]["stolen_status"] == "LISTED"
        assert risky_data["canonical_fields"]["writeoff_status"] == "STATUTORY"
        print(f"      Stolen: {risky_data['canonical_fields']['stolen_status']}")
        print(f"      Writeoff: {risky_data['canonical_fields']['writeoff_status']}")

        exp_risky = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": "1FA6P8CF8H5000000", "field_name": "writeoff_status"},
        )
        exp_risky_data = _extract_tool_payload(exp_risky)
        assert exp_risky_data["outcome"] == "RESOLVED"
        assert exp_risky_data["value"] == "STATUTORY"
        outcome = exp_risky_data["outcome"]
        val = exp_risky_data["value"]
        print(f"      Explanation outcome: {outcome} ({val})")

        # Scenario 3: Unknown Vehicle
        print("\n[5/8] Scenario 3: Unknown Vehicle (JM0BL10F000000000)")
        res_unk = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": "JM0BL10F000000000"},
        )
        unk_data = _extract_tool_payload(res_unk)
        assert unk_data["canonical_fields"]["ppsr_result"] == "UNKNOWN"
        ppsr = unk_data["canonical_fields"]["ppsr_result"]
        print(f"      PPSR Result: {ppsr} (preserved as UNKNOWN)")

        exp_unk = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": "JM0BL10F000000000", "field_name": "ppsr_result"},
        )
        exp_unk_data = _extract_tool_payload(exp_unk)
        assert exp_unk_data["outcome"] == "RESOLVED"
        assert exp_unk_data["value"] == "UNKNOWN"

        exp_absent = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": "JM0BL10F000000000", "field_name": "non_existent_field"},
        )
        exp_absent_data = _extract_tool_payload(exp_absent)
        assert exp_absent_data["outcome"] == "ABSENT"
        print(f"      Absent field explanation: {exp_absent_data['outcome']}")

        # Scenario 4: Conflict Vehicle
        print(f"\n[6/8] Scenario 4: Conflict Vehicle ({conflict_vin})")
        res_conf = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": conflict_vin},
        )
        conf_data = _extract_tool_payload(res_conf)
        conflict_fields = [c["field_name"] for c in conf_data.get("conflicts", [])]
        assert "ppsr_result" in conflict_fields
        print(f"      Active conflicts detected: {', '.join(conflict_fields)}")

        exp_conf = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": conflict_vin, "field_name": "ppsr_result"},
        )
        exp_conf_data = _extract_tool_payload(exp_conf)
        assert exp_conf_data["outcome"] == "UNRESOLVED"
        conflicts = exp_conf_data.get("conflicts", [])
        assert len(conflicts) >= 1
        competing = [
            c["value"] for conflict in conflicts for c in conflict.get("conflicting_candidates", [])
        ]
        assert len(competing) >= 2
        print(f"      Conflict explanation outcome: {exp_conf_data['outcome']}")
        print(f"      Competing values preserved: {competing}")

        # Scenario 5: History, Revisions, and Observations
        print(f"\n[7/8] Scenario 5: Vehicle History and Revisions ({temporal_vin})")
        hist_res = await stdio_client.call_tool(
            "get_vehicle_history",
            arguments={"vin": temporal_vin, "limit": 10},
        )
        hist_data = _extract_tool_payload(hist_res)
        assert isinstance(hist_data, list)
        rev_numbers = [r["revision_number"] for r in hist_data]
        assert rev_numbers == [2, 1], f"Expected revisions [2, 1], got {rev_numbers}"
        print(f"      History returned revisions: {rev_numbers}")

        # Check latest revision (Rev 2)
        rev2 = hist_data[0]
        assert rev2["revision_number"] == 2
        assert rev2["canonical_fields"]["asking_price_cents"] == 1995000
        assert rev2["canonical_fields"]["odometer_km"] == 52300

        # Check earlier revision (Rev 1)
        rev1 = hist_data[1]
        assert rev1["revision_number"] == 1
        assert rev1["canonical_fields"]["asking_price_cents"] == 2150000

        # Point-in-time exact revision 1 retrieval
        rev1_res = await stdio_client.call_tool(
            "get_vehicle_revision",
            arguments={"vin": temporal_vin, "revision_number": 1},
        )
        rev1_data = _extract_tool_payload(rev1_res)
        assert rev1_data["revision_number"] == 1
        assert rev1_data["canonical_fields"]["asking_price_cents"] == 2150000
        p1 = rev1_data["canonical_fields"]["asking_price_cents"]
        print(f"      Fetched exact revision 1 (price: {p1})")

        # Point-in-time exact revision 2 retrieval
        rev2_res = await stdio_client.call_tool(
            "get_vehicle_revision",
            arguments={"vin": temporal_vin, "revision_number": 2},
        )
        rev2_data = _extract_tool_payload(rev2_res)
        assert rev2_data["revision_number"] == 2
        assert rev2_data["canonical_fields"]["asking_price_cents"] == 1995000
        assert rev2_data["canonical_fields"]["odometer_km"] == 52300
        p2 = rev2_data["canonical_fields"]["asking_price_cents"]
        odo2 = rev2_data["canonical_fields"]["odometer_km"]
        print(f"      Fetched exact revision 2 (price: {p2}, odo: {odo2})")

        # Pick observation_id from Revision 2 asking_price_cents provenance
        obs_id = None
        prov2_list = rev2_data.get("field_provenance", {}).get("asking_price_cents", [])
        if prov2_list and prov2_list[0].get("observation_id"):
            obs_id = prov2_list[0]["observation_id"]
        assert obs_id is not None, "Revision 2 provenance must name the update observation ID!"

        print(f"\n[8/8] Scenario 6: Exact Source Observation ({obs_id})")
        obs_res = await stdio_client.call_tool(
            "get_source_observation",
            arguments={"observation_id": obs_id},
        )
        obs_data = _extract_tool_payload(obs_res)
        assert obs_data["observation_id"] == obs_id
        assert "raw_payload" in obs_data
        src = obs_data["source_system"]
        has_payload = bool(obs_data["raw_payload"])
        print(f"      Observation source: {src}, payload verified: {has_payload}")

    # Check Streamable HTTP transport
    print("\n[HTTP Parity] Testing Streamable HTTP endpoint...")
    async with (
        httpx2.AsyncClient(timeout=10.0) as http_client,
        streamable_http_client(http_url, http_client=http_client) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as http_session,
    ):
        await http_session.initialize()
        http_tools_res = await http_session.list_tools()
        http_tool_names = sorted([t.name for t in http_tools_res.tools])
        assert http_tool_names == stdio_tool_names, (
            f"HTTP tools mismatch: {http_tool_names} != {stdio_tool_names}"
        )
        print(f"      HTTP tools match stdio catalog: {', '.join(http_tool_names)}")

        # Test list_vehicles parity over HTTP
        h_cat = await http_session.call_tool(
            "list_vehicles",
            arguments={"limit": 20, "offset": 0},
        )
        h_cat_data = _extract_tool_payload(h_cat)
        assert h_cat_data == catalog, (
            "HTTP list_vehicles response must match stdio catalog discovery exactly"
        )
        print("      HTTP list_vehicles matches stdio discovery outcome!")

        # Test clean lookup parity
        h_res = await http_session.call_tool(
            "lookup_vehicle",
            arguments={"vin": "1HGCR2F85HA000000"},
        )
        h_data = _extract_tool_payload(h_res)
        assert h_data == data, (
            "HTTP lookup_vehicle response must match stdio canonical lookup exactly"
        )
        print("      HTTP lookup_vehicle matches stdio canonical outcome!")

    print("\n==================================================================")
    print(" Demonstration completed successfully! All evidence preserved.")
    print("==================================================================")


async def run_remote_smoke(http_url: str = "http://127.0.0.1:8080/mcp") -> None:
    """Execute public/remote Streamable HTTP smoke test verifying all six tools and evidence."""
    print("==================================================================")
    print(" Vehicle Intelligence MCP Server — Public Smoke Verification")
    print("==================================================================")
    print(f"Target URL: {http_url}")

    async with (
        httpx2.AsyncClient(timeout=10.0) as http_client,
        streamable_http_client(http_url, http_client=http_client) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as http_session,
    ):
        await http_session.initialize()
        http_tools_res = await http_session.list_tools()
        tool_names = sorted([t.name for t in http_tools_res.tools])
        assert len(tool_names) == 6, f"Expected 6 tools, got {len(tool_names)}: {tool_names}"
        print(f"==> Discovered 6 MCP tools over remote Streamable HTTP: {', '.join(tool_names)}")

        # 1. Catalog discovery
        cat_res = await http_session.call_tool(
            "list_vehicles", arguments={"limit": 20, "offset": 0}
        )
        catalog = _extract_tool_payload(cat_res)
        assert isinstance(catalog, dict)
        assert catalog.get("total") == 5, f"Expected 5 vehicles, got {catalog.get('total')}"
        items = catalog.get("items", [])
        print(f"==> Catalog discovery passed: {len(items)} items verified")

        # 2. Canonical lookup
        clean_vin = next(item["vin"] for item in items if item.get("make") == "HONDA")
        lookup_res = await http_session.call_tool("lookup_vehicle", arguments={"vin": clean_vin})
        lookup_data = _extract_tool_payload(lookup_res)
        assert lookup_data.get("vin") == clean_vin
        assert lookup_data.get("canonical_fields", {}).get("make") == "HONDA"
        print(f"==> Canonical lookup passed for {clean_vin}")

        # 3. Field explanation
        explain_res = await http_session.call_tool(
            "explain_vehicle_field",
            arguments={"vin": clean_vin, "field_name": "color"},
        )
        explain_data = _extract_tool_payload(explain_res)
        assert explain_data.get("outcome") in ("RESOLVED", "UNRESOLVED", "ABSENT")
        print(f"==> Field explanation passed for {clean_vin}.color")

        # 4. History
        temporal_vin = next(item["vin"] for item in items if item.get("revision_number", 1) >= 2)
        hist_res = await http_session.call_tool(
            "get_vehicle_history", arguments={"vin": temporal_vin}
        )
        hist_data = _extract_tool_payload(hist_res)
        assert isinstance(hist_data, list)
        assert len(hist_data) >= 2, "Expected at least 2 revisions in history"
        print(f"==> History retrieval passed: {len(hist_data)} revisions verified")

        # 5. Revision
        rev_res = await http_session.call_tool(
            "get_vehicle_revision",
            arguments={"vin": temporal_vin, "revision_number": 1},
        )
        rev_data = _extract_tool_payload(rev_res)
        assert rev_data.get("revision_number") == 1
        print("==> Exact revision retrieval passed")

        # 6. Source observation (safe metadata inspection, NEVER printing raw payload)
        obs_id = next(
            provenance["observation_id"]
            for entries in rev_data.get("field_provenance", {}).values()
            for provenance in entries
            if provenance.get("observation_id")
        )
        obs_res = await http_session.call_tool(
            "get_source_observation",
            arguments={"observation_id": obs_id},
        )
        obs_data = _extract_tool_payload(obs_res)
        assert obs_data.get("observation_id") == obs_id
        assert "raw_payload" in obs_data
        source_sys = obs_data.get("source_system")
        print(f"==> Source observation passed: {obs_id} (source: {source_sys}, payload verified)")

    print("==================================================================")
    print(" Public smoke verification PASSED! All 6 tools verified.")
    print("==================================================================")


def main() -> None:
    """CLI entrypoint for running the demonstration."""
    import sys

    if "--remote-url" in sys.argv:
        idx = sys.argv.index("--remote-url")
        target_url = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "http://127.0.0.1:8080/mcp"
        asyncio.run(run_remote_smoke(http_url=target_url))
    else:
        asyncio.run(run_demonstration())


if __name__ == "__main__":
    main()
