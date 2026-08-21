"""Small-dependency request correlation and redaction-safe structured logging."""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping
from uuid import uuid4


SERVICE_NAME = "cwl-grc"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TRACEPARENT_PATTERN = re.compile(r"^(?P<version>[0-9a-f]{2})-(?P<trace>[0-9a-f]{32})-(?P<span>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$")
request_logger = logging.getLogger("cwl_grc.request")
_verified_principal: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "cwl_grc_verified_principal",
    default=None,
)
_request_state: contextvars.ContextVar[MutableMapping[str, Any] | None] = contextvars.ContextVar(
    "cwl_grc_request_state",
    default=None,
)
_PRINCIPAL_STATE_KEY = "verified_principal"


@dataclass(frozen=True)
class RequestContext:
    """Validated W3C trace and bounded request identifiers for one request."""

    request_id: str
    traceparent: str


def build_request_context(request_id: str | None, traceparent: str | None) -> RequestContext:
    """Preserve valid correlation headers or generate safe replacements."""
    safe_request_id = request_id if _valid_request_id(request_id) else uuid4().hex
    safe_traceparent = traceparent if _valid_traceparent(traceparent) else _new_traceparent()
    return RequestContext(safe_request_id, safe_traceparent)


def set_request_state(state: MutableMapping[str, Any]) -> contextvars.Token:
    """Bind the shared ASGI request state across synchronous worker calls."""
    return _request_state.set(state)


def reset_request_state(token: contextvars.Token) -> None:
    """Restore the previous request-state binding after request logging."""
    _request_state.reset(token)


def set_verified_principal(
    tenant_id: str | None,
    actor_id: str | None,
) -> contextvars.Token:
    """Store a request-local principal reference without retaining raw values in logs."""
    principal = None if tenant_id is None or actor_id is None else (tenant_id, actor_id)
    state = _request_state.get()
    if state is not None:
        state[_PRINCIPAL_STATE_KEY] = principal
    return _verified_principal.set(principal)


def reset_verified_principal(token: contextvars.Token) -> None:
    """Restore the previous request-local principal context."""
    _verified_principal.reset(token)


def principal_reference() -> str | None:
    """Return a short one-way reference for the verified tenant and actor pair."""
    state = _request_state.get()
    principal = _verified_principal.get() if state is None else state.get(_PRINCIPAL_STATE_KEY)
    if principal is None:
        return None
    return hashlib.sha256(f"{principal[0]}:{principal[1]}".encode("utf-8")).hexdigest()[:16]


def emit_request_log(
    context: RequestContext,
    method: str,
    route: str,
    status_code: int,
    latency_ms: float,
    environment: str,
    error_class: str | None = None,
    traceparent: str | None = None,
) -> None:
    """Emit one JSON log record without tokens, keys, plaintext, or raw identifiers."""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "ERROR" if status_code >= 500 else "INFO",
        "service": SERVICE_NAME,
        "version": "0.1.0",
        "environment": environment,
        "request_id": context.request_id,
        "traceparent": traceparent or context.traceparent,
        "method": method,
        "route": route,
        "status_code": status_code,
        "outcome": "error" if status_code >= 400 else "success",
        "latency_ms": round(latency_ms, 3),
        "principal_reference": principal_reference(),
        "error_class": error_class,
    }
    request_logger.info(json.dumps(payload, sort_keys=True))


def route_template(scope: Mapping[str, Any]) -> str:
    """Return a registered route template without exposing raw path identifiers."""
    route_path = getattr(scope.get("route"), "path", None)
    if isinstance(route_path, str) and route_path.startswith("/"):
        return route_path
    return "unmatched"


def _valid_request_id(value: str | None) -> bool:
    """Return whether a caller-supplied request ID is bounded and log-safe."""
    return value is not None and REQUEST_ID_PATTERN.fullmatch(value) is not None


def _valid_traceparent(value: str | None) -> bool:
    """Validate the W3C traceparent shape and reject all-zero identifiers."""
    if value is None:
        return False
    match = TRACEPARENT_PATTERN.fullmatch(value)
    if match is None or match["version"] == "ff":
        return False
    return (
        set(match["trace"]) != {"0"}
        and set(match["span"]) != {"0"}
    )


def _new_traceparent() -> str:
    """Generate a valid W3C version-zero traceparent with sampled-off flags."""
    return f"00-{uuid4().hex}-{secrets.token_hex(8)}-01"
