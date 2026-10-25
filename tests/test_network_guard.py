"""The dashboard binds 0.0.0.0 so that `tailscale serve` (loopback) and a phone hitting the
tailnet address directly both work. Its unauthenticated admin routes must still never answer
the LAN, so the restriction lives in the app instead of the bind address."""

import httpx
import pytest

from backend.main import app, client_is_allowed


async def _health_from(client_addr: tuple[str, int]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=client_addr)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/health")


async def test_loopback_and_tailnet_clients_are_served():
    for addr in [("127.0.0.1", 1234), ("100.97.48.126", 1234)]:
        response = await _health_from(addr)
        assert response.status_code == 200, addr
        assert response.json() == {"ok": True}


async def test_lan_clients_are_refused():
    for addr in [("192.168.7.220", 1234), ("10.0.0.5", 1234), ("8.8.8.8", 1234)]:
        response = await _health_from(addr)
        assert response.status_code == 403, addr


@pytest.mark.parametrize(
    "host, allowed",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),  # IPv4-mapped loopback
        ("100.64.0.1", True),  # bottom of the Tailscale CGNAT range
        ("100.127.255.254", True),  # top of it
        ("fd7a:115c:a1e0::1", True),  # Tailscale IPv6
        ("100.63.255.255", False),  # just below the range
        ("100.128.0.0", False),  # just above it
        ("192.168.7.220", False),
        ("172.16.0.1", False),
        ("8.8.8.8", False),
        ("not-an-ip", False),
        (None, False),
    ],
)
def test_client_is_allowed(host, allowed):
    assert client_is_allowed(host) is allowed
