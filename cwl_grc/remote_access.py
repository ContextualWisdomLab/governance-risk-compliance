"""Fail-closed network boundary for the unauthenticated developer preview."""

from __future__ import annotations

import os
from ipaddress import ip_address
from pathlib import Path
from typing import Any


KEYVERSE_REQUIRED_VALUES = frozenset({"1", "true", "yes"})
KEYVERSE_OPTIONAL_VALUES = frozenset({"", "0", "false", "no"})


def keyverse_start_is_required() -> bool:
    """Return whether this process must start with a Keyverse verifier and TLS."""
    raw = os.environ.get("CWL_GRC_REQUIRE_KEYVERSE", "").strip().lower()
    if raw in KEYVERSE_REQUIRED_VALUES:
        return True
    if raw in KEYVERSE_OPTIONAL_VALUES:
        return False
    raise ValueError(
        "CWL_GRC_REQUIRE_KEYVERSE must be 1, true, yes, 0, false, no, or unset."
    )


def startup_next_action() -> str:
    """Return the operator next action that matches the failed local start."""
    try:
        required = keyverse_start_is_required()
    except ValueError:
        required = True
    if required:
        return (
            "Set CWL_GRC_REQUIRE_KEYVERSE to 1, true, yes, 0, false, no, or unset; "
            "set CWL_GRC_EVIDENCE_KEY for a persistent store; set "
            "CWL_GRC_KEYVERSE_ISSUER, CWL_GRC_KEYVERSE_AUDIENCE, "
            "CWL_GRC_KEYVERSE_CLIENT_IDS, CWL_GRC_KEYVERSE_JWKS_PATH, "
            "CWL_GRC_TLS_CERTFILE, and CWL_GRC_TLS_KEYFILE to readable files; "
            "use a numeric PORT; set CWL_GRC_ACCESS_TOKEN for CLI writes; "
            "and keep the bind on 127.0.0.1."
        )
    return (
        "Set CWL_GRC_EVIDENCE_KEY for a persistent store, use a numeric PORT, "
        "and keep the bind on 127.0.0.1."
    )


def request_uses_encrypted_transport(scheme: str | None) -> bool:
    """Accept only HTTPS. Forwarded proto headers are not a TLS substitute."""
    return (scheme or "").lower() == "https"


def loopback_port() -> int:
    """Parse ``PORT`` as a TCP port and fail closed on a non-numeric value."""
    raw = os.environ.get("PORT", "8080")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("PORT must be a numeric TCP port.") from exc


def loopback_server_bind() -> dict[str, Any]:
    """Return the loopback Uvicorn bind, requiring TLS when Keyverse is required."""
    settings: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": loopback_port(),
        "proxy_headers": False,
    }
    if not keyverse_start_is_required():
        return settings
    cert = os.environ.get("CWL_GRC_TLS_CERTFILE", "").strip()
    key = os.environ.get("CWL_GRC_TLS_KEYFILE", "").strip()
    if not cert or not key:
        raise ValueError(
            "TLS certificate and key files are required when CWL_GRC_REQUIRE_KEYVERSE is set."
        )
    cert_path = Path(cert)
    key_path = Path(key)
    if not cert_path.is_file() or not key_path.is_file():
        raise ValueError("TLS certificate and key files must be readable files.")
    settings["ssl_certfile"] = str(cert_path)
    settings["ssl_keyfile"] = str(key_path)
    return settings


def request_is_local(
    client_host: str | None,
    forwarded_for: str | None,
    forwarded: str | None,
    forwarded_proto: str | None = None,
    forwarded_host: str | None = None,
) -> bool:
    """Accept only direct loopback requests with no proxy forwarding evidence."""
    if forwarded_for or forwarded or forwarded_proto or forwarded_host:
        return False
    if client_host in {"localhost", "testclient"}:
        return True
    if client_host is None:
        return False
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False
