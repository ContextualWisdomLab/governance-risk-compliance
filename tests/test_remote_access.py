"""Regression tests for the fail-closed developer-preview network boundary."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.remote_access import (
    keyverse_start_is_required,
    loopback_server_bind,
    request_is_local,
    request_uses_encrypted_transport,
)


def test_local_request_classifier_fails_closed() -> None:
    """Only direct loopback and the in-process test client count as local."""
    assert request_is_local("testclient", None, None) is True
    assert request_is_local("localhost", None, None) is True
    assert request_is_local("127.0.0.1", None, None) is True
    assert request_is_local("::1", None, None) is True
    assert request_is_local("198.51.100.23", None, None) is False
    assert request_is_local("not-an-address", None, None) is False
    assert request_is_local(None, None, None) is False
    assert request_is_local("127.0.0.1", "198.51.100.23", None) is False
    assert request_is_local("127.0.0.1", None, "for=198.51.100.23") is False


def test_forwarded_remote_preview_is_always_denied(monkeypatch) -> None:  # noqa: ANN001
    """No environment value can expose the unauthenticated HTTP surface."""
    monkeypatch.setenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", "1")
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))

    local = client.get("/healthz")
    forwarded = client.get(
        "/healthz",
        headers={"X-Forwarded-For": "198.51.100.23"},
    )
    standardized = client.get(
        "/healthz",
        headers={"Forwarded": "for=198.51.100.23"},
    )

    assert local.status_code == 200
    for response in (forwarded, standardized):
        assert response.status_code == 503
        assert response.json() == {
            "detail": (
                "Remote preview is disabled. Configure Keyverse-backed identity and "
                "tenant authorization before exposing CWL GRC."
            )
        }


def test_keyverse_required_start_rejects_header_identity(monkeypatch) -> None:  # noqa: ANN001
    """Declared actor headers cannot boot a Keyverse-required process."""
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "1")
    assert keyverse_start_is_required() is True
    with pytest.raises(ValueError, match="Keyverse access-token verifier"):
        create_app(database_url="sqlite://", evidence_key=None)


def test_keyverse_required_start_admits_https_and_rejects_http(
    monkeypatch,
) -> None:  # noqa: ANN001
    """Keyverse-required loopback still needs TLS; HTTP healthz is not an exception."""
    from cwl_grc.keyverse_authentication import (
        KeyverseAccessTokenSettings,
        KeyverseAccessTokenVerifier,
        parse_keyverse_jwks,
    )

    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "true")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    now = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)
    verifier = KeyverseAccessTokenVerifier(
        KeyverseAccessTokenSettings(
            issuer="https://identity.example.test/realms/cwl",
            audience="cwl-grc-api",
            allowed_client_ids=frozenset({"cwl-grc-web"}),
            allowed_roles=frozenset({"compliance_officer"}),
        ),
        parse_keyverse_jwks(json.dumps({"keys": [public_jwk]}).encode()),
        now=lambda: now,
    )
    app = create_app(
        database_url="sqlite://",
        evidence_key=None,
        access_token_verifier=verifier,
    )
    http_client = TestClient(app)
    denied = http_client.get("/healthz")
    assert denied.status_code == 503
    assert "Encrypted transport" in denied.json()["detail"]
    https_client = TestClient(app, base_url="https://testserver")
    healthy = https_client.get("/healthz")
    assert healthy.status_code == 200
    assert healthy.json() == {"status": "ok", "service": "cwl-grc"}


def test_loopback_bind_requires_tls_files_when_keyverse_is_required(
    monkeypatch,
) -> None:  # noqa: ANN001
    """A Keyverse-required start cannot bind HTTP even on 127.0.0.1."""
    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    assert keyverse_start_is_required() is False
    assert request_uses_encrypted_transport("https") is True
    assert request_uses_encrypted_transport("http") is False
    assert request_uses_encrypted_transport(None) is False
    preview = loopback_server_bind()
    assert preview == {"host": "127.0.0.1", "port": 8080}
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "yes")
    monkeypatch.setenv("PORT", "8443")
    with pytest.raises(ValueError, match="TLS certificate"):
        loopback_server_bind()
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", "grc.crt")
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", "grc.key")
    hardened = loopback_server_bind()
    assert hardened == {
        "host": "127.0.0.1",
        "port": 8443,
        "ssl_certfile": "grc.crt",
        "ssl_keyfile": "grc.key",
    }


def test_cli_serve_fails_closed_when_keyverse_required_without_tls(
    monkeypatch, capsys
) -> None:  # noqa: ANN001
    """Officer CLI states the next action instead of binding HTTP under Keyverse."""
    from cwl_grc.cli import serve_http

    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "1")
    monkeypatch.setenv(
        "CWL_GRC_EVIDENCE_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    assert serve_http() == 2
    missing_tls = json.loads(capsys.readouterr().out)
    assert "TLS" in missing_tls["error"]
    assert "127.0.0.1" in missing_tls["next_action"]
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", "grc.crt")
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", "grc.key")
    assert serve_http() == 2
    missing_verifier = json.loads(capsys.readouterr().out)
    assert "verifier" in missing_verifier["error"]
    assert "Keyverse verifier" in missing_verifier["next_action"]
