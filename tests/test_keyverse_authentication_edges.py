"""Edge and failure-path coverage for the Keyverse access-token verifier."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cwl_grc.keyverse_authentication import (
    AccessTokenValidationError,
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)


ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
NOW = datetime(2026, 8, 19, 3, 0, tzinfo=timezone.utc)


def _key_material(kid: str = "key-1") -> tuple[Any, dict[str, Any]]:
    """Create one RSA signing key and public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _settings(**overrides: Any) -> KeyverseAccessTokenSettings:
    """Create the first-profile verification settings."""
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "allowed_client_ids": frozenset({CLIENT_ID}),
        "allowed_roles": frozenset({"compliance_officer"}),
        "clock_skew_seconds": 60,
    }
    values.update(overrides)
    return KeyverseAccessTokenSettings(**values)


def _claims(now: datetime = NOW, **overrides: Any) -> dict[str, Any]:
    """Create one valid human access-token claim set."""
    values: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "subject-1",
        "aud": AUDIENCE,
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "iat": int((now - timedelta(seconds=1)).timestamp()),
        "jti": "token-1",
        "client_id": CLIENT_ID,
        "scope": "openid grc.policy.read",
        "role": "compliance_officer",
        "org": "tenant-1",
        "workspace": "workspace-1",
        "principal_kind": "human",
    }
    values.update(overrides)
    return values


def _token(
    private_key: Any,
    *,
    claims: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> str:
    """Sign one token with default closed-profile headers."""
    return jwt.encode(
        claims or _claims(),
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "key-1", **(headers or {})},
    )


def _verifier(
    jwk: dict[str, Any],
    *,
    now: Any = lambda: NOW,
) -> KeyverseAccessTokenVerifier:
    """Build a verifier around one public JWK and clock."""
    key_set = parse_keyverse_jwks(json.dumps({"keys": [jwk]}).encode())
    return KeyverseAccessTokenVerifier(_settings(), key_set, now=now)


def test_header_decode_missing_kid_bad_signature_and_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed header, missing key ID, bad signature, and non-object payload fail."""
    private_key, jwk = _key_material()
    verifier = _verifier(jwk)
    with pytest.raises(AccessTokenValidationError, match="header"):
        verifier.verify("not-a-jwt")

    no_kid = jwt.encode(
        _claims(),
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt"},
    )
    with pytest.raises(AccessTokenValidationError, match="key identifier"):
        verifier.verify(no_kid)

    attacker_key, _attacker_jwk = _key_material("attacker")
    with pytest.raises(AccessTokenValidationError, match="signature"):
        verifier.verify(_token(attacker_key))

    monkeypatch.setattr(jwt, "get_unverified_header", lambda _token: [])
    with pytest.raises(AccessTokenValidationError, match="header"):
        verifier.verify(_token(private_key))
    monkeypatch.setattr(
        jwt,
        "get_unverified_header",
        lambda _token: {"alg": "RS256", "typ": "at+jwt", "kid": "key-1"},
    )
    monkeypatch.setattr(jwt, "decode", lambda *_args, **_kwargs: [])
    with pytest.raises(AccessTokenValidationError, match="payload"):
        verifier.verify(_token(private_key))


def test_numeric_date_types_overflow_optional_nbf_and_clock_awareness() -> None:
    """NumericDate types, overflow, optional nbf, and the verifier clock are strict."""
    private_key, jwk = _key_material()
    verifier = _verifier(jwk)
    invalid_cases = (
        (_claims(exp=True), "expiration"),
        (_claims(iat=1.5), "issued-at"),
        (_claims(nbf=False), "not-before"),
        (_claims(exp=10**100), "expiration"),
    )
    for claims, message in invalid_cases:
        with pytest.raises(AccessTokenValidationError, match=message):
            verifier.verify(_token(private_key, claims=claims))

    without_nbf = _claims()
    without_nbf.pop("nbf")
    assert verifier.verify(_token(private_key, claims=without_nbf)).actor_id == "subject-1"

    naive_clock = _verifier(jwk, now=lambda: datetime(2026, 8, 19, 3, 0))
    with pytest.raises(AccessTokenValidationError, match="timezone-aware"):
        naive_clock.verify(_token(private_key))


def test_default_clock_and_application_media_type_are_supported() -> None:
    """The production UTC clock and full registered media type both validate."""
    private_key, jwk = _key_material()
    actual_now = datetime.now(timezone.utc)
    claims = _claims(actual_now)
    token = _token(
        private_key,
        claims=claims,
        headers={"typ": "application/at+jwt"},
    )
    key_set = parse_keyverse_jwks(json.dumps({"keys": [jwk]}).encode())
    verifier = KeyverseAccessTokenVerifier(_settings(), key_set)
    assert verifier.verify(token).token_id == "token-1"


def test_jwks_object_shape_and_malformed_rsa_key_are_rejected() -> None:
    """The JWK parser rejects a non-object root, non-object key, and missing RSA data."""
    _private_key, jwk = _key_material()
    for document in (b"[]", b'{"keys": [null]}'):
        with pytest.raises(AccessTokenValidationError, match="JWK set"):
            parse_keyverse_jwks(document)
    malformed = dict(jwk)
    malformed.pop("n")
    with pytest.raises(AccessTokenValidationError, match="malformed"):
        parse_keyverse_jwks(json.dumps({"keys": [malformed]}).encode())


def test_non_string_private_claims_and_invalid_settings_entries_are_rejected() -> None:
    """Authorization claims and allowlist members are never coerced from other types."""
    private_key, jwk = _key_material()
    verifier = _verifier(jwk)
    for claims, label in (
        (_claims(sub=123), "subject"),
        (_claims(client_id=123), "client"),
        (_claims(role=["compliance_officer"]), "role"),
        (_claims(org=123), "tenant"),
        (_claims(workspace=123), "workspace"),
        (_claims(jti=123), "token identifier"),
        (_claims(principal_kind=123), "principal kind"),
    ):
        with pytest.raises(AccessTokenValidationError, match=label):
            verifier.verify(_token(private_key, claims=claims))

    for setting_overrides, message in (
        ({"issuer": "https://user@identity.example.test/realms/cwl"}, "HTTPS issuer"),
        ({"issuer": f"{ISSUER}?query=1"}, "HTTPS issuer"),
        ({"issuer": f"{ISSUER}#fragment"}, "HTTPS issuer"),
        ({"allowed_client_ids": frozenset({""})}, "client"),
        ({"allowed_roles": frozenset({""})}, "role"),
        ({"clock_skew_seconds": -1}, "clock skew"),
    ):
        with pytest.raises(ValueError, match=message):
            _settings(**setting_overrides)
