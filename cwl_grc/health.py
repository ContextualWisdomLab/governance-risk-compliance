"""Liveness probe for standalone and modular deployments."""

from __future__ import annotations

from typing import Any


def health_payload() -> dict[str, Any]:
    """Return the /healthz body used by orchestrators and local probes."""
    return {"status": "ok", "service": "cwl-grc"}
