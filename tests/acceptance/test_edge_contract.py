"""Acceptance contract test asserting Cloudflare edge controls, DNS, WAF, and rate limits."""

import json
from pathlib import Path


def test_edge_contract_configuration_exists_and_is_valid() -> None:
    edge_path = Path("deploy/cloudflare-edge.json")
    assert edge_path.exists(), "deploy/cloudflare-edge.json must exist"
    data = json.loads(edge_path.read_text())
    assert isinstance(data, dict), "Edge contract must be a valid JSON object"


def test_edge_contract_hostnames_and_proxy_status() -> None:
    edge_path = Path("deploy/cloudflare-edge.json")
    data = json.loads(edge_path.read_text())

    # DNS configuration
    dns_records = data.get("dns_records", [])
    assert len(dns_records) >= 1, "Must configure at least one public DNS record"
    for record in dns_records:
        assert record.get("proxied") is True, "Public demo hostnames must be Cloudflare-proxied"
        name = record.get("name", "")
        assert "*" not in name, f"Hostnames must not contain wildcards: {name}"


def test_edge_contract_tls_and_security_ruleset() -> None:
    edge_path = Path("deploy/cloudflare-edge.json")
    data = json.loads(edge_path.read_text())

    # Strict TLS
    tls = data.get("tls", {})
    assert tls.get("mode") in ("strict", "full_strict"), (
        "Edge TLS must use strict origin validation"
    )

    # WAF ruleset
    waf = data.get("waf", {})
    assert waf.get("free_managed_ruleset") is True, "Free Managed Ruleset must be enabled"


def test_edge_contract_cache_bypass_for_dynamic_routes() -> None:
    edge_path = Path("deploy/cloudflare-edge.json")
    data = json.loads(edge_path.read_text())

    cache_rules = data.get("cache_rules", [])
    assert len(cache_rules) >= 1, "Must configure cache bypass rules"
    bypassed_paths = [r.get("path") for r in cache_rules if r.get("action") == "bypass"]
    assert any("/mcp" in p for p in bypassed_paths if p), "MCP endpoint must bypass edge cache"


def test_edge_contract_one_free_rate_limiting_rule() -> None:
    edge_path = Path("deploy/cloudflare-edge.json")
    data = json.loads(edge_path.read_text())

    rate_limits = data.get("rate_limiting_rules", [])
    assert len(rate_limits) == 1, (
        f"Cloudflare Free plan supports exactly 1 rate-limit rule, got {len(rate_limits)}"
    )

    rule = rate_limits[0]
    assert rule.get("characteristics") == ["ip"] or rule.get("counting") == "ip", (
        "Free rate limit rule must count per IP"
    )
    assert rule.get("requests_per_period") == 60, "Rate limit threshold must be 60 requests"
    assert rule.get("period_seconds") == 60, "Rate limit period must be 60 seconds"
    assert rule.get("action") in ("block", "challenge", "429"), (
        "Rate limit action must reject traffic"
    )
    assert "/mcp" in rule.get("path", ""), "Rate limit rule must cover /mcp path"
