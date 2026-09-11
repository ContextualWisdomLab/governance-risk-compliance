"""Verify closed-profile Keyverse JWT access tokens without trusting caller headers."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

import jwt


MAX_JWKS_BYTES = 1024 * 1024
MAX_CLOCK_SKEW_SECONDS = 300
ACCESS_TOKEN_TYPES = frozenset({"at+jwt", "application/at+jwt"})
REQUIRED_ACCESS_TOKEN_CLAIMS = (
    "iss",
    "sub",
    "aud",
    "exp",
    "iat",
    "jti",
    "client_id",
    "scope",
    "role",
    "org",
    "workspace",
    "principal_kind",
)
PRIVATE_RSA_PARAMETERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth"})


class AccessTokenValidationError(ValueError):
    """Signal that untrusted bearer material failed a closed validation rule."""


@dataclass(frozen=True)
class KeyverseAccessTokenSettings:
    """Immutable resource-server policy for one Keyverse access-token profile."""

    issuer: str
    audience: str
    allowed_client_ids: frozenset[str]
    allowed_roles: frozenset[str]
    clock_skew_seconds: int = 60

    def __post_init__(self) -> None:
        """Reject ambiguous issuer, audience, client, role, and clock policy."""
        parsed = urlsplit(self.issuer)
        if (
            self.issuer != self.issuer.strip()
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Keyverse requires one exact HTTPS issuer URL.")
        if not self.audience or self.audience != self.audience.strip():
            raise ValueError("Keyverse requires one exact non-empty resource audience.")
        if not self.allowed_client_ids or any(
            not client_id or client_id != client_id.strip()
            for client_id in self.allowed_client_ids
        ):
            raise ValueError("Keyverse requires an exact non-empty allowed client set.")
        if not self.allowed_roles or any(
            not role or role != role.strip() for role in self.allowed_roles
        ):
            raise ValueError("Keyverse requires an exact non-empty allowed role set.")
        if (
            isinstance(self.clock_skew_seconds, bool)
            or not isinstance(self.clock_skew_seconds, int)
            or not 0 <= self.clock_skew_seconds <= MAX_CLOCK_SKEW_SECONDS
        ):
            raise ValueError("Keyverse clock skew must be between 0 and 300 seconds.")


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Verified Keyverse identity and authorization context for one human caller."""

    tenant_id: str
    actor_id: str
    client_id: str
    role: str
    workspace_id: str
    scopes: frozenset[str]
    token_id: str
    issued_at: datetime
    expires_at: datetime
    principal_kind: str


@dataclass(frozen=True)
class KeyverseJwkSet:
    """Immutable public signing-key map indexed by a unique Keyverse key ID."""

    keys_by_id: Mapping[str, jwt.PyJWK]


class KeyverseAccessTokenVerifier:
    """Validate signed RFC 9068-style Keyverse access tokens for CWL GRC.

    Bearer access tokens remain reusable by default; callers that require
    one-time use can provide an atomic JTI check-and-record guard.
    """

    def __init__(
        self,
        settings: KeyverseAccessTokenSettings,
        key_set: KeyverseJwkSet,
        *,
        now: Callable[[], datetime] | None = None,
        token_replay_guard: Callable[[str], bool] | None = None,
    ) -> None:
        """Bind policy, reviewed keys, clock, and an optional caller-owned replay guard."""
        self._settings = settings
        self._key_set = key_set
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._token_replay_guard = token_replay_guard

    def verify(
        self,
        token: str,
        *,
        required_scopes: Collection[str] = (),
    ) -> AuthenticatedPrincipal:
        """Return a principal after validation and action-scope checks before replay use."""
        header = _read_untrusted_header(token)
        key_id = _validated_header_key_id(header)
        signing_key = self._key_set.keys_by_id.get(key_id)
        if signing_key is None:
            raise AccessTokenValidationError("The Keyverse signing key is unknown.")
        payload = _decode_verified_payload(token, signing_key, self._settings)
        now = _normalized_utc(self._now(), "verification clock")
        issued_at = _numeric_date(payload["iat"], "issued-at")
        expires_at = _numeric_date(payload["exp"], "expiration")
        if expires_at <= issued_at:
            raise AccessTokenValidationError(
                "The Keyverse access-token time bounds are invalid."
            )
        skew = timedelta(seconds=self._settings.clock_skew_seconds)
        try:
            expiration_boundary = expires_at + skew
        except OverflowError as exc:
            raise AccessTokenValidationError(
                "The Keyverse expiration claim is invalid."
            ) from exc
        if now >= expiration_boundary:
            raise AccessTokenValidationError("The Keyverse access token is expired.")
        clock_skew_boundary = _clock_skew_boundary(now, skew)
        if "nbf" in payload:
            not_before = _numeric_date(payload["nbf"], "not-before")
            if not_before >= expires_at:
                raise AccessTokenValidationError(
                    "The Keyverse access-token time bounds are invalid."
                )
            if clock_skew_boundary < not_before:
                raise AccessTokenValidationError("The Keyverse access token is not active.")
        if issued_at > clock_skew_boundary:
            raise AccessTokenValidationError("The Keyverse issued-at time is in the future.")

        actor_id = _required_text(payload, "sub", "subject")
        client_id = _required_text(payload, "client_id", "client")
        if client_id not in self._settings.allowed_client_ids:
            raise AccessTokenValidationError("The Keyverse client is not authorized.")
        if actor_id == client_id:
            raise AccessTokenValidationError(
                "The Keyverse subject cannot impersonate the OAuth client."
            )
        role = _required_text(payload, "role", "role")
        if role not in self._settings.allowed_roles:
            raise AccessTokenValidationError("The Keyverse role is not authorized.")
        tenant_id = _required_text(payload, "org", "tenant")
        workspace_id = _required_text(payload, "workspace", "workspace")
        token_id = _required_text(payload, "jti", "token identifier")
        principal_kind = _required_text(
            payload,
            "principal_kind",
            "principal kind",
        )
        if principal_kind != "human":
            raise AccessTokenValidationError(
                "This Keyverse profile accepts a human principal only."
            )
        scopes = _parse_scopes(payload["scope"])
        principal = AuthenticatedPrincipal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            client_id=client_id,
            role=role,
            workspace_id=workspace_id,
            scopes=scopes,
            token_id=token_id,
            issued_at=issued_at,
            expires_at=expires_at,
            principal_kind=principal_kind,
        )
        require_access_scopes(principal, required_scopes)
        if self._token_replay_guard is not None and self._token_replay_guard(token_id):
            raise AccessTokenValidationError("The Keyverse access token was replayed.")
        return principal


def parse_keyverse_jwks(
    document: bytes,
    *,
    maximum_bytes: int = MAX_JWKS_BYTES,
) -> KeyverseJwkSet:
    """Parse a bounded public RSA signing-key set and reject ambiguity or secrets."""
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or not 0 < maximum_bytes <= MAX_JWKS_BYTES
    ):
        raise AccessTokenValidationError("The Keyverse JWK size limit is invalid.")
    if len(document) > maximum_bytes:
        raise AccessTokenValidationError("The Keyverse JWK set is too large.")
    try:
        payload = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AccessTokenValidationError("The Keyverse JWK set is malformed.") from exc
    if not isinstance(payload, dict):
        raise AccessTokenValidationError("The Keyverse JWK set must be an object.")
    raw_keys = payload.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise AccessTokenValidationError("The Keyverse JWK set needs public keys.")

    keys_by_id: dict[str, jwt.PyJWK] = {}
    for raw_key in raw_keys:
        if not isinstance(raw_key, dict):
            raise AccessTokenValidationError(
                "The Keyverse JWK set contains a non-object key."
            )
        key_id = raw_key.get("kid")
        if (
            not isinstance(key_id, str)
            or not key_id
            or key_id != key_id.strip()
        ):
            raise AccessTokenValidationError(
                "Each Keyverse JWK needs one exact key identifier."
            )
        if key_id in keys_by_id:
            raise AccessTokenValidationError(
                "The Keyverse JWK set has a duplicate key identifier."
            )
        if (
            raw_key.get("kty") != "RSA"
            or raw_key.get("use") != "sig"
            or raw_key.get("alg") != "RS256"
            or PRIVATE_RSA_PARAMETERS.intersection(raw_key)
        ):
            raise AccessTokenValidationError(
                "The Keyverse JWK must be a public RS256 signing key."
            )
        try:
            parsed_key = jwt.PyJWK.from_dict(raw_key, algorithm="RS256")
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise AccessTokenValidationError("The Keyverse JWK is malformed.") from exc
        keys_by_id[key_id] = parsed_key
    return KeyverseJwkSet(MappingProxyType(keys_by_id))


def require_access_scopes(
    principal: AuthenticatedPrincipal,
    required_scopes: Collection[str],
) -> None:
    """Reject an authenticated principal missing any action-specific scope."""
    missing = set(required_scopes).difference(principal.scopes)
    if missing:
        raise AccessTokenValidationError("The Keyverse token lacks a required scope.")


def _read_untrusted_header(token: str) -> dict[str, Any]:
    """Decode only enough untrusted header data to choose a reviewed public key."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AccessTokenValidationError("The Keyverse token header is malformed.") from exc
    if not isinstance(header, dict):
        raise AccessTokenValidationError("The Keyverse token header is malformed.")
    if "crit" in header:
        raise AccessTokenValidationError(
            "The Keyverse token uses an unsupported critical header."
        )
    if header.get("alg") != "RS256":
        raise AccessTokenValidationError("The Keyverse token must use RS256.")
    token_type = header.get("typ")
    if not isinstance(token_type, str) or token_type.casefold() not in ACCESS_TOKEN_TYPES:
        raise AccessTokenValidationError(
            "The Keyverse token does not declare an access-token type."
        )
    return header


def _validated_header_key_id(header: Mapping[str, Any]) -> str:
    """Return one exact non-empty signing-key identifier from the header policy."""
    key_id = header.get("kid")
    if (
        not isinstance(key_id, str)
        or not key_id
        or key_id != key_id.strip()
    ):
        raise AccessTokenValidationError(
            "The Keyverse token needs one exact signing key identifier."
        )
    return key_id


def _decode_verified_payload(
    token: str,
    signing_key: jwt.PyJWK,
    settings: KeyverseAccessTokenSettings,
) -> dict[str, Any]:
    """Verify signature, issuer, audience, and required access-token claims."""
    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.audience,
            issuer=settings.issuer,
            options={
                "require": list(REQUIRED_ACCESS_TOKEN_CLAIMS),
                "verify_signature": True,
                "verify_iss": True,
                "verify_aud": True,
                "strict_aud": True,
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )
    except jwt.MissingRequiredClaimError as exc:
        raise AccessTokenValidationError(
            "The Keyverse token is missing a required claim."
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise AccessTokenValidationError("The Keyverse token issuer is invalid.") from exc
    except jwt.InvalidAudienceError as exc:
        raise AccessTokenValidationError("The Keyverse token audience is invalid.") from exc
    except jwt.PyJWTError as exc:
        raise AccessTokenValidationError(
            "The Keyverse token signature or payload is invalid."
        ) from exc
    if not isinstance(payload, dict):
        raise AccessTokenValidationError("The Keyverse token payload is malformed.")
    return payload


def _required_text(payload: Mapping[str, Any], claim: str, label: str) -> str:
    """Return one exact non-empty string claim without normalizing signed values."""
    value = payload.get(claim)
    if not isinstance(value, str) or not value or value != value.strip():
        raise AccessTokenValidationError(f"The Keyverse {label} is invalid.")
    return value


def _parse_scopes(value: Any) -> frozenset[str]:
    """Parse the RFC 6749 space-delimited scope string without accepting arrays."""
    if not isinstance(value, str):
        raise AccessTokenValidationError("The Keyverse scope claim is invalid.")
    scopes = frozenset(scope for scope in value.split(" ") if scope)
    if not scopes:
        raise AccessTokenValidationError("The Keyverse scope claim is empty.")
    return scopes


def _numeric_date(value: Any, label: str) -> datetime:
    """Parse one integral NumericDate and reject booleans, fractions, and overflow."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccessTokenValidationError(f"The Keyverse {label} claim is invalid.")
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise AccessTokenValidationError(
            f"The Keyverse {label} claim is invalid."
        ) from exc


def _clock_skew_boundary(now: datetime, skew: timedelta) -> datetime:
    """Add configured clock skew without leaking a datetime overflow."""
    try:
        return now + skew
    except OverflowError as exc:
        raise AccessTokenValidationError(
            "The Keyverse clock-skew boundary is invalid."
        ) from exc


def _normalized_utc(value: datetime, label: str) -> datetime:
    """Require a clock with a defined UTC offset and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise AccessTokenValidationError(f"The Keyverse {label} must be timezone-aware.")
    return value.astimezone(timezone.utc)
