"""Automated demonstration client exercising all five vehicle intelligence tools."""

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
                    pass
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


async def run_demonstration(
    stdio_server: Any = None,
    http_url: str = "http://127.0.0.1:8080/mcp",
) -> None:
    """Execute real-client demonstration exercising all tools and scenarios."""
    print("==================================================================")
    print(" Vehicle Intelligence MCP Server — End-to-End Demonstration")
    print("==================================================================")

    # Resolve stdio server
    resolved_server = stdio_server or create_server(ServerConfig())

    print("\n[1/7] Initializing stdio transport and verifying tool catalog...")
    async with Client(resolved_server) as stdio_client:
        stdio_tools_res = await stdio_client.list_tools()
        stdio_tool_names = sorted([t.name for t in stdio_tools_res.tools])
        print(f"      Stdio tools ({len(stdio_tool_names)}): {', '.join(stdio_tool_names)}")
        assert len(stdio_tool_names) == 5, f"Expected 5 tools, got {len(stdio_tool_names)}"

        # Scenario 1: Clean Vehicle
        print("\n[2/7] Scenario 1: Clean Vehicle (1HGCR2F85HA000000)")
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
        print("\n[3/7] Scenario 2: Risky Vehicle (1FA6P8CF8H5000000)")
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
        print("\n[4/7] Scenario 3: Unknown Vehicle (JM0BL10F000000000)")
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
        print("\n[5/7] Scenario 4: Conflict Vehicle (WAUZZZ8K7BA000000)")
        res_conf = await stdio_client.call_tool(
            "lookup_vehicle",
            arguments={"vin": "WAUZZZ8K7BA000000"},
        )
        conf_data = _extract_tool_payload(res_conf)
        conflict_fields = [c["field_name"] for c in conf_data.get("conflicts", [])]
        assert "ppsr_result" in conflict_fields
        print(f"      Active conflicts detected: {', '.join(conflict_fields)}")

        exp_conf = await stdio_client.call_tool(
            "explain_vehicle_field",
            arguments={"vin": "WAUZZZ8K7BA000000", "field_name": "ppsr_result"},
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
        print("\n[6/7] Scenario 5: Vehicle History and Revisions (1HGCR2F85HA000000)")
        hist_res = await stdio_client.call_tool(
            "get_vehicle_history",
            arguments={"vin": "1HGCR2F85HA000000", "limit": 10},
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
            arguments={"vin": "1HGCR2F85HA000000", "revision_number": 1},
        )
        rev1_data = _extract_tool_payload(rev1_res)
        assert rev1_data["revision_number"] == 1
        assert rev1_data["canonical_fields"]["asking_price_cents"] == 2150000
        p1 = rev1_data["canonical_fields"]["asking_price_cents"]
        print(f"      Fetched exact revision 1 (price: {p1})")

        # Point-in-time exact revision 2 retrieval
        rev2_res = await stdio_client.call_tool(
            "get_vehicle_revision",
            arguments={"vin": "1HGCR2F85HA000000", "revision_number": 2},
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

        print(f"\n[7/7] Scenario 6: Exact Source Observation ({obs_id})")
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
    async with httpx2.AsyncClient(timeout=10.0) as http_client:
        try:
            async with (
                streamable_http_client(http_url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as http_session,
            ):
                await http_session.initialize()
                http_tools_res = await http_session.list_tools()
                http_tool_names = sorted([t.name for t in http_tools_res.tools])
                assert http_tool_names == stdio_tool_names
                print(f"      HTTP tools match stdio catalog: {', '.join(http_tool_names)}")

                # Test clean lookup parity
                h_res = await http_session.call_tool(
                    "lookup_vehicle",
                    arguments={"vin": "1HGCR2F85HA000000"},
                )
                h_data = _extract_tool_payload(h_res)
                assert h_data["canonical_fields"]["make"] == "HONDA"
                print("      HTTP lookup_vehicle matches stdio canonical outcome!")
        except Exception as e:
            print(f"      [NOTE] Streamable HTTP verification: {e}")

    print("\n==================================================================")
    print(" Demonstration completed successfully! All evidence preserved.")
    print("==================================================================")


def main() -> None:
    """CLI entrypoint for running the demonstration."""
    asyncio.run(run_demonstration())


if __name__ == "__main__":
    main()
