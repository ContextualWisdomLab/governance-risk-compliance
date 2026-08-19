"""Security regressions for the Keyverse JWT access-token verification kernel."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cwl_grc.keyverse_authentication import (
    AccessTokenValidationError,
    AuthenticatedPrincipal,
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
    require_access_scopes,
)


NOW = datetime(2026, 8, 19, 3, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"


def _new_signing_material(kid: str) -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and its public RFC 7517 representation."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _settings() -> KeyverseAccessTokenSettings:
    """Return the closed first-profile resource-server policy."""
    return KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({"compliance_officer", "grc_auditor"}),
        clock_skew_seconds=60,
    )


def _claims(**overrides: Any) -> dict[str, Any]:
    """Return one RFC 9068-compatible human access-token claim set."""
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "keyverse-subject-019d",
        "aud": AUDIENCE,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((NOW - timedelta(seconds=5)).timestamp()),
        "iat": int((NOW - timedelta(seconds=5)).timestamp()),
        "jti": "token-019d",
        "client_id": CLIENT_ID,
        "scope": "openid grc.policy.read grc.policy.write grc.evidence.write",
        "role": "compliance_officer",
        "org": "tenant-acme",
        "workspace": "grc-primary",
        "principal_kind": "human",
    }
    claims.update(overrides)
    return claims


def _token(
    private_key: Any,
    *,
    kid: str = "key-1",
    typ: str = "at+jwt",
    claims: dict[str, Any] | None = None,
    extra_headers: dict[str, Any] | None = None,
) -> str:
    """Sign one access token with an explicit type and key identifier."""
    headers = {"kid": kid, "typ": typ, **(extra_headers or {})}
    return jwt.encode(
        claims or _claims(),
        private_key,
        algorithm="RS256",
        headers=headers,
    )


def _verifier(*jwks: dict[str, Any]) -> KeyverseAccessTokenVerifier:
    """Build the verifier from a bounded public JWK set."""
    document = json.dumps({"keys": list(jwks)}).encode("utf-8")
    return KeyverseAccessTokenVerifier(
        _settings(),
        parse_keyverse_jwks(document),
        now=lambda: NOW,
    )


def test_valid_keyverse_access_token_becomes_tenant_principal() -> None:
    """A valid access token supplies verified identity, tenant, role, and scopes."""
    private_key, jwk = _new_signing_material("key-1")
    principal = _verifier(jwk).verify(_token(private_key))

    assert principal == AuthenticatedPrincipal(
        tenant_id="tenant-acme",
        actor_id="keyverse-subject-019d",
        client_id=CLIENT_ID,
        role="compliance_officer",
        workspace_id="grc-primary",
        scopes=frozenset(
            {
                "openid",
                "grc.policy.read",
                "grc.policy.write",
                "grc.evidence.write",
            }
        ),
        token_id="token-019d",
        issued_at=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=5),
        principal_kind="human",
    )
    require_access_scopes(principal, {"grc.policy.write"})


def test_scope_gate_fails_closed_for_missing_or_empty_scope() -> None:
    """Authorization requires every requested action scope."""
    private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    principal = verifier.verify(_token(private_key))
    with pytest.raises(AccessTokenValidationError, match="required scope"):
        require_access_scopes(principal, {"grc.evidence.read"})
    with pytest.raises(AccessTokenValidationError, match="scope"):
        verifier.verify(_token(private_key, claims=_claims(scope="")))
    with pytest.raises(AccessTokenValidationError, match="scope"):
        verifier.verify(_token(private_key, claims=_claims(scope=["openid"])))


def test_cross_jwt_confusion_and_critical_headers_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ID tokens, untyped tokens, and unsupported critical headers never authenticate."""
    private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    for typ in ("JWT", "id+jwt", ""):
        with pytest.raises(AccessTokenValidationError, match="access-token type"):
            verifier.verify(_token(private_key, typ=typ))

    critical_token = _token(
        private_key,
        extra_headers={"crit": ["example"], "example": True},
    )
    with pytest.raises(AccessTokenValidationError, match="header"):
        verifier.verify(critical_token)

    monkeypatch.setattr(
        jwt,
        "get_unverified_header",
        lambda _token: {
            "alg": "RS256",
            "typ": "at+jwt",
            "kid": "key-1",
            "crit": ["example"],
        },
    )
    with pytest.raises(AccessTokenValidationError, match="critical"):
        verifier.verify(_token(private_key))


def test_unsigned_and_wrong_algorithm_tokens_are_rejected() -> None:
    """The resource server accepts only signed RS256 access tokens."""
    _private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    unsigned = jwt.encode(
        _claims(),
        key="",
        algorithm="none",
        headers={"typ": "at+jwt"},
    )
    with pytest.raises(AccessTokenValidationError, match="RS256"):
        verifier.verify(unsigned)

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "at+jwt", "kid": "key-1"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(_claims()).encode()).rstrip(b"=")
    forged = b".".join((header, payload, b"forged")).decode()
    with pytest.raises(AccessTokenValidationError, match="RS256"):
        verifier.verify(forged)


def test_issuer_audience_time_and_required_claims_fail_closed() -> None:
    """RFC 9068 validation rejects tokens for another resource or time window."""
    private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    invalid_cases = (
        (_claims(iss="https://attacker.invalid"), "issuer"),
        (_claims(aud="another-api"), "audience"),
        (_claims(exp=int((NOW - timedelta(minutes=2)).timestamp())), "expired"),
        (_claims(nbf=int((NOW + timedelta(minutes=2)).timestamp())), "not active"),
        (_claims(iat=int((NOW + timedelta(minutes=2)).timestamp())), "issued-at"),
    )
    for claims, message in invalid_cases:
        with pytest.raises(AccessTokenValidationError, match=message):
            verifier.verify(_token(private_key, claims=claims))

    for missing in (
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
    ):
        claims = _claims()
        claims.pop(missing)
        with pytest.raises(AccessTokenValidationError, match="required claim"):
            verifier.verify(_token(private_key, claims=claims))


def test_unknown_ambiguous_or_ineligible_signing_keys_are_rejected() -> None:
    """A token must resolve to exactly one eligible public RSA signing key."""
    private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    with pytest.raises(AccessTokenValidationError, match="signing key"):
        verifier.verify(_token(private_key, kid="missing"))

    duplicate = dict(jwk)
    with pytest.raises(AccessTokenValidationError, match="duplicate key identifier"):
        parse_keyverse_jwks(json.dumps({"keys": [jwk, duplicate]}).encode())

    for mutation in (
        {"use": "enc"},
        {"alg": "RS512"},
        {"kty": "oct", "k": "c2VjcmV0"},
        {"d": "private-material"},
        {"kid": ""},
    ):
        candidate = {**jwk, **mutation}
        with pytest.raises(AccessTokenValidationError, match="JWK"):
            parse_keyverse_jwks(json.dumps({"keys": [candidate]}).encode())


def test_jwks_document_is_bounded_well_formed_and_rotation_safe() -> None:
    """Multiple reviewed keys support rotation without accepting malformed input."""
    old_private, old_jwk = _new_signing_material("old-key")
    new_private, new_jwk = _new_signing_material("new-key")
    verifier = _verifier(old_jwk, new_jwk)

    assert verifier.verify(_token(old_private, kid="old-key")).actor_id == (
        "keyverse-subject-019d"
    )
    assert verifier.verify(_token(new_private, kid="new-key")).actor_id == (
        "keyverse-subject-019d"
    )
    for document in (
        b"not-json",
        b"{}",
        b'{"keys": "wrong"}',
        b'{"keys": []}',
        b'{"keys": [null]}',
    ):
        with pytest.raises(AccessTokenValidationError, match="JWK set"):
            parse_keyverse_jwks(document)
    with pytest.raises(AccessTokenValidationError, match="too large"):
        parse_keyverse_jwks(b"x" * (1024 * 1024 + 1))


def test_client_role_tenant_workspace_and_principal_kind_are_closed() -> None:
    """Private authorization claims use bounded non-empty values and allowlists."""
    private_key, jwk = _new_signing_material("key-1")
    verifier = _verifier(jwk)
    invalid_cases = (
        (_claims(client_id="unregistered-client"), "client"),
        (_claims(role="system_admin"), "role"),
        (_claims(org=""), "tenant"),
        (_claims(workspace=""), "workspace"),
        (_claims(principal_kind="service"), "human"),
        (_claims(sub=CLIENT_ID), "subject"),
        (_claims(jti=""), "token identifier"),
    )
    for claims, message in invalid_cases:
        with pytest.raises(AccessTokenValidationError, match=message):
            verifier.verify(_token(private_key, claims=claims))


def test_settings_reject_unsafe_or_ambiguous_configuration() -> None:
    """Issuer, resource, client, role, and clock policy are explicit."""
    with pytest.raises(ValueError, match="HTTPS issuer"):
        KeyverseAccessTokenSettings(
            issuer="http://identity.invalid",
            audience=AUDIENCE,
            allowed_client_ids=frozenset({CLIENT_ID}),
            allowed_roles=frozenset({"compliance_officer"}),
        )
    with pytest.raises(ValueError, match="audience"):
        KeyverseAccessTokenSettings(
            issuer=ISSUER,
            audience="",
            allowed_client_ids=frozenset({CLIENT_ID}),
            allowed_roles=frozenset({"compliance_officer"}),
        )
    with pytest.raises(ValueError, match="client"):
        KeyverseAccessTokenSettings(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_client_ids=frozenset(),
            allowed_roles=frozenset({"compliance_officer"}),
        )
    with pytest.raises(ValueError, match="role"):
        KeyverseAccessTokenSettings(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_client_ids=frozenset({CLIENT_ID}),
            allowed_roles=frozenset(),
        )
    with pytest.raises(ValueError, match="clock skew"):
        KeyverseAccessTokenSettings(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_client_ids=frozenset({CLIENT_ID}),
            allowed_roles=frozenset({"compliance_officer"}),
            clock_skew_seconds=301,
        )
