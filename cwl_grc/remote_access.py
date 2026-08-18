"""Fail-closed network boundary for the unauthenticated developer preview."""

from __future__ import annotations

import os
from ipaddress import ip_address

REMOTE_PREVIEW_ENV = "CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def remote_preview_enabled() -> bool:
    """Return whether an operator explicitly enabled unauthenticated remote preview."""
    return os.environ.get(REMOTE_PREVIEW_ENV, "").strip().casefold() in _TRUE_VALUES


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
