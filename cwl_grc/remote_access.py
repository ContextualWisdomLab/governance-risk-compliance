"""Fail-closed network boundary for the unauthenticated developer preview."""

from __future__ import annotations

from ipaddress import ip_address


def request_is_local(
    client_host: str | None,
    forwarded_for: str | None,
    forwarded: str | None,
) -> bool:
    """Accept only direct loopback requests with no proxy forwarding evidence."""
    if forwarded_for or forwarded:
        return False
    if client_host in {"localhost", "testclient"}:
        return True
    if client_host is None:
        return False
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False
