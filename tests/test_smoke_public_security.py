"""`smoke-public.sh --security` against an ingress that has no separate origin host.

A fake HTTP server on IPv6 loopback stands in for a platform ingress: it answers
an unknown Host with 404, rejects hostile Origins, and rejects oversized bodies.
`[::1]` is not treated as a local URL by the script, so the remote probes run.
"""

import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

SCRIPT = "scripts/smoke-public.sh"
NORTHFLANK_HOST = "vehicle-mcp-server.sandbox.northflank.app"


class IngressHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        host = self.headers.get("Host", "")
        if self.headers.get("Origin"):
            self.send_response(403)
        elif int(self.headers.get("Content-Length", "0")) > 1_000_000:
            self.send_response(400)
        elif host != f"[::1]:{self.server.server_port}":
            self.send_response(404)
        else:
            self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


class IPv6Server(HTTPServer):
    address_family = socket.AF_INET6


@pytest.fixture
def ingress_url() -> Iterator[str]:
    server = IPv6Server(("::1", 0), IngressHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://[::1]:{server.server_port}/mcp"
    finally:
        server.shutdown()
        server.server_close()


def run_security(url: str, direct_origin_host: str | None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "PUBLIC_MCP_URL": url}
    if direct_origin_host is not None:
        env["PUBLIC_MCP_DIRECT_ORIGIN_HOST"] = direct_origin_host
    return subprocess.run(
        ["bash", SCRIPT, "--security"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=60,
    )


def test_opt_out_skips_direct_origin_probe_and_accepts_ingress_404(ingress_url: str) -> None:
    result = run_security(ingress_url, "none")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Hostile Host header rejected (HTTP 404)" in result.stdout
    assert "Direct-origin bypass probe skipped" in result.stdout


def test_default_still_probes_northflank_host(ingress_url: str) -> None:
    result = run_security(ingress_url, None)
    assert result.returncode == 1
    assert "direct-origin bypass attempt" in result.stdout
    assert "got: 404" in result.stdout


def test_explicit_host_is_probed(ingress_url: str) -> None:
    result = run_security(ingress_url, NORTHFLANK_HOST)
    assert result.returncode == 1
    assert "direct-origin bypass attempt" in result.stdout
