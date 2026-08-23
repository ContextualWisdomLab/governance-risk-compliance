"""Request correlation identifiers that never copy Keyverse access tokens."""

from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4


MAX_CORRELATION_LENGTH = 128
ALLOWED_CORRELATION_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)
_CORRELATION_REFERENCE: ContextVar[str | None] = ContextVar(
    "cwl_grc_correlation_reference",
    default=None,
)


def looks_like_access_token(value: str) -> bool:
    """Return whether a string resembles compact JWT access-token material."""
    return value.count(".") >= 2 and "eyJ" in value


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
