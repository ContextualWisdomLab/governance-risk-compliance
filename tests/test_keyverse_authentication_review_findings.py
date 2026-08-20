"""Regression tests for current-head Keyverse authentication review findings."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cwl_grc.keyverse_authentication import (
    MAX_JWKS_BYTES,
    AccessTokenValidationError,
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)


NOW = datetime(2026, 8, 19, 6, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"


def _material() -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and its reviewed public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _claims(**overrides: Any) -> dict[str, Any]:
    """Return one otherwise valid human access-token claim set."""
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "subject-1",
        "aud": AUDIENCE,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
        "iat": int((NOW - timedelta(seconds=1)).timestamp()),
        "jti": "token-1",
        "client_id": CLIENT_ID,
        "scope": "openid grc.policy.read",
        "role": "compliance_officer",
        "org": "tenant-1",
        "workspace": "workspace-1",
        "principal_kind": "human",
    }
    claims.update(overrides)
    return claims


def _token(
    private_key: Any,
    claims: dict[str, Any],
    *,
    typ: str = "at+jwt",
    kid: str = "key-1",
) -> str:
    """Sign one token for the reviewed resource-server profile."""
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"typ": typ, "kid": kid},
    )


def _verifier(jwk: dict[str, Any]) -> KeyverseAccessTokenVerifier:
    """Build the closed verifier with a deterministic UTC clock."""
    key_set = parse_keyverse_jwks(json.dumps({"keys": [jwk]}).encode())
    settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({"compliance_officer"}),
        clock_skew_seconds=60,
    )
    return KeyverseAccessTokenVerifier(settings, key_set, now=lambda: NOW)


def test_impossible_access_token_time_windows_are_rejected_before_clock_skew() -> None:
    """An access token must contain a strictly positive potential validity interval."""
    private_key, jwk = _material()
    verifier = _verifier(jwk)
    issued_at = int((NOW - timedelta(seconds=30)).timestamp())
    impossible = (
        _claims(iat=issued_at, exp=issued_at),
        _claims(iat=issued_at, exp=issued_at - 1),
        _claims(
            iat=issued_at,
            nbf=int((NOW + timedelta(seconds=30)).timestamp()),
            exp=int((NOW + timedelta(seconds=30)).timestamp()),
        ),
        _claims(
            iat=issued_at,
            nbf=int((NOW + timedelta(seconds=31)).timestamp()),
            exp=int((NOW + timedelta(seconds=30)).timestamp()),
        ),
    )
    for claims in impossible:
        with pytest.raises(AccessTokenValidationError, match="time bounds"):
            verifier.verify(_token(private_key, claims))


def test_expiration_skew_overflow_fails_closed_as_validation_error() -> None:
    """A maximum representable NumericDate cannot leak a datetime OverflowError."""
    private_key, jwk = _material()
    verifier = _verifier(jwk)
    with pytest.raises(AccessTokenValidationError, match="expiration claim"):
        verifier.verify(_token(private_key, _claims(exp=253402300799)))


def test_jwks_parser_cannot_raise_the_hard_one_mebibyte_limit() -> None:
    """The caller may lower the JWK limit but can never raise or disable it."""
    _private_key, jwk = _material()
    document = json.dumps({"keys": [jwk]}).encode()
    assert parse_keyverse_jwks(document, maximum_bytes=len(document)).keys_by_id
    for invalid_limit in (True, 0, -1, 1.5, MAX_JWKS_BYTES + 1):
        with pytest.raises(AccessTokenValidationError, match="JWK size limit"):
            parse_keyverse_jwks(document, maximum_bytes=invalid_limit)  # type: ignore[arg-type]


def test_access_token_audience_is_one_exact_string_not_an_array() -> None:
    """A token for multiple resources cannot authenticate to this closed profile."""
    private_key, jwk = _material()
    verifier = _verifier(jwk)
    with pytest.raises(AccessTokenValidationError, match="audience"):
        verifier.verify(_token(private_key, _claims(aud=[AUDIENCE])))
    with pytest.raises(AccessTokenValidationError, match="audience"):
        verifier.verify(_token(private_key, _claims(aud=[AUDIENCE, "another-api"])))


def test_signed_identifier_claims_with_edge_whitespace_are_rejected_not_trimmed() -> None:
    """The resource server preserves exact Keyverse identifier and role semantics."""
    private_key, jwk = _material()
    verifier = _verifier(jwk)
    for claim_name in (
        "sub",
        "client_id",
        "role",
        "org",
        "workspace",
        "jti",
        "principal_kind",
    ):
        original = str(_claims()[claim_name])
        for altered in (f" {original}", f"{original} "):
            with pytest.raises(AccessTokenValidationError, match="invalid"):
                verifier.verify(_token(private_key, _claims(**{claim_name: altered})))


def test_registered_full_access_token_media_type_remains_supported() -> None:
    """The full registered `application/at+jwt` type remains a positive contract."""
    private_key, jwk = _material()
    principal = _verifier(jwk).verify(
        _token(private_key, _claims(), typ="application/at+jwt")
    )
    assert principal.actor_id == "subject-1"


def test_resource_server_settings_reject_edge_whitespace_without_normalizing() -> None:
    """Configured issuer, audience, clients, and roles retain exact signed semantics."""
    invalid_settings = (
        {
            "issuer": f"{ISSUER} ",
            "audience": AUDIENCE,
            "allowed_client_ids": frozenset({CLIENT_ID}),
            "allowed_roles": frozenset({"compliance_officer"}),
        },
        {
            "issuer": ISSUER,
            "audience": f" {AUDIENCE}",
            "allowed_client_ids": frozenset({CLIENT_ID}),
            "allowed_roles": frozenset({"compliance_officer"}),
        },
        {
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "allowed_client_ids": frozenset({f"{CLIENT_ID} "}),
            "allowed_roles": frozenset({"compliance_officer"}),
        },
        {
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "allowed_client_ids": frozenset({CLIENT_ID}),
            "allowed_roles": frozenset({" compliance_officer"}),
        },
    )
    for values in invalid_settings:
        with pytest.raises(ValueError, match="exact"):
            KeyverseAccessTokenSettings(**values)


def test_jwk_and_token_key_identifiers_reject_edge_whitespace() -> None:
    """Key selection never silently normalizes an untrusted `kid` identifier."""
    private_key, jwk = _material()
    for altered in (" key-1", "key-1 "):
        altered_jwk = dict(jwk)
        altered_jwk["kid"] = altered
        with pytest.raises(AccessTokenValidationError, match="key identifier"):
            parse_keyverse_jwks(json.dumps({"keys": [altered_jwk]}).encode())

        with pytest.raises(AccessTokenValidationError, match="key identifier"):
            _verifier(jwk).verify(_token(private_key, _claims(), kid=altered))
