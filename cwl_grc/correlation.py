"""Request correlation identifiers that never copy Keyverse access tokens."""

from __future__ import annotations

import base64
import json
from contextvars import ContextVar, Token
from uuid import uuid4


MAX_CORRELATION_LENGTH = 128
ALLOWED_CORRELATION_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)
_COMPACT_JWS_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)
_CORRELATION_REFERENCE: ContextVar[str | None] = ContextVar(
    "cwl_grc_correlation_reference",
    default=None,
)


def _is_json_object_segment(segment: str) -> bool:
    """Return whether one dot-separated segment is a base64url-encoded JSON object."""
    if not segment or set(segment) - _COMPACT_JWS_CHARACTERS:
        return False
    try:
        decoded = base64.b64decode(
            segment + "=" * (-len(segment) % 4),
            altchars=b"-_",
            validate=True,
        )
        document = json.loads(decoded)
    except ValueError:
        return False
    return isinstance(document, dict)


def looks_like_access_token(value: str) -> bool:
    """Return whether a string has the structure of a compact JWS access token.

    Detection is structural rather than a substring search: a compact JWT is
    exactly three base64url segments whose header and payload decode to JSON
    objects. Trusted identifiers that only mention ``eyJ`` are not rejected.
    """
    segments = value.split(".")
    if len(segments) != 3:
        return False
    header, payload, _signature = segments
    return _is_json_object_segment(header) and _is_json_object_segment(payload)


def normalize_correlation_reference(value: str | None) -> str:
    """Return a safe correlation reference, generating one when the header is unusable."""
    if (
        isinstance(value, str)
        and value
        and value == value.strip()
        and len(value) <= MAX_CORRELATION_LENGTH
        and set(value) <= ALLOWED_CORRELATION_CHARACTERS
        and not looks_like_access_token(value)
    ):
        return value
    return uuid4().hex


def bind_request_correlation(header_value: str | None) -> Token[str | None]:
    """Bind one request correlation reference for the current execution context."""
    return _CORRELATION_REFERENCE.set(normalize_correlation_reference(header_value))


def reset_request_correlation(token: Token[str | None]) -> None:
    """Clear the request correlation bound by ``bind_request_correlation``."""
    _CORRELATION_REFERENCE.reset(token)


def current_correlation_reference() -> str:
    """Return the bound correlation reference, generating one when the context is empty."""
    value = _CORRELATION_REFERENCE.get()
    if value:
        return value
    generated = uuid4().hex
    _CORRELATION_REFERENCE.set(generated)
    return generated
