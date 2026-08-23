"""Fail-closed network boundary for the unauthenticated developer preview."""

from __future__ import annotations

import os
from ipaddress import ip_address
from typing import Any


def keyverse_start_is_required() -> bool:
    """Return whether this process must start with a Keyverse verifier and TLS."""
    return os.environ.get("CWL_GRC_REQUIRE_KEYVERSE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def request_uses_encrypted_transport(scheme: str | None) -> bool:
    """Accept only HTTPS. Forwarded proto headers are not a TLS substitute."""
    return (scheme or "").lower() == "https"


def loopback_server_bind() -> dict[str, Any]:
    """Return the loopback Uvicorn bind, requiring TLS when Keyverse is required."""
    settings: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": int(os.environ.get("PORT", "8080")),
    }
    if not keyverse_start_is_required():
        return settings
    cert = os.environ.get("CWL_GRC_TLS_CERTFILE", "").strip()
    key = os.environ.get("CWL_GRC_TLS_KEYFILE", "").strip()
    if not cert or not key:
        raise ValueError(
            "TLS certificate and key files are required when CWL_GRC_REQUIRE_KEYVERSE is set."
        )
    settings["ssl_certfile"] = cert
    settings["ssl_keyfile"] = key
    return settings


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
