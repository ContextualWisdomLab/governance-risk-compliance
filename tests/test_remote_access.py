"""Regression tests for the fail-closed developer-preview network boundary."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.remote_access import (
    keyverse_start_is_required,
    loopback_port,
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
    assert request_is_local("127.0.0.1", None, None, "https") is False
    assert request_is_local("127.0.0.1", None, None, None, "example.test") is False


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
    forwarded_proto = client.get(
        "/healthz",
        headers={"X-Forwarded-Proto": "https"},
    )

    assert local.status_code == 200
    for response in (forwarded, standardized, forwarded_proto):
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


def _write_tls_files(tmp_path) -> tuple[Path, Path]:  # noqa: ANN001
    """Write readable TLS path placeholders used by the hardened local start."""
    cert = tmp_path / "grc.crt"
    key = tmp_path / "grc.key"
    cert.write_text("certificate", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    return cert, key


def test_loopback_bind_requires_tls_files_when_keyverse_is_required(
    monkeypatch,
    tmp_path,
) -> None:  # noqa: ANN001
    """A Keyverse-required start cannot bind HTTP even on 127.0.0.1."""
    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    assert keyverse_start_is_required() is False
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "0")
    assert keyverse_start_is_required() is False
    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    assert request_uses_encrypted_transport("https") is True
    assert request_uses_encrypted_transport("http") is False
    assert request_uses_encrypted_transport(None) is False
    preview = loopback_server_bind()
    assert preview == {"host": "127.0.0.1", "port": 8080, "proxy_headers": False}
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(ValueError, match="numeric TCP port"):
        loopback_port()
    with pytest.raises(ValueError, match="numeric TCP port"):
        loopback_server_bind()
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "yes")
    monkeypatch.setenv("PORT", "8443")
    with pytest.raises(ValueError, match="TLS certificate"):
        loopback_server_bind()
    missing_cert = tmp_path / "missing.crt"
    missing_key = tmp_path / "missing.key"
    cert, key = _write_tls_files(tmp_path)
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(missing_cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    with pytest.raises(ValueError, match="readable files"):
        loopback_server_bind()
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(missing_key))
    with pytest.raises(ValueError, match="readable files"):
        loopback_server_bind()
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    hardened = loopback_server_bind()
    assert hardened == {
        "host": "127.0.0.1",
        "port": 8443,
        "proxy_headers": False,
        "ssl_certfile": str(cert),
        "ssl_keyfile": str(key),
    }


def test_cli_serve_fails_closed_when_keyverse_required_without_tls(
    monkeypatch, capsys, tmp_path
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
    assert "CWL_GRC_EVIDENCE_KEY" in missing_tls["next_action"]
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(tmp_path / "missing.crt"))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(tmp_path / "missing.key"))
    assert serve_http() == 2
    missing_files = json.loads(capsys.readouterr().out)
    assert "readable files" in missing_files["error"]
    assert "CWL_GRC_TLS_CERTFILE" in missing_files["next_action"]
    cert, key = _write_tls_files(tmp_path)
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    assert serve_http() == 2
    missing_verifier = json.loads(capsys.readouterr().out)
    assert "JWKS" in missing_verifier["error"]
    assert "CWL_GRC_KEYVERSE_JWKS_PATH" in missing_verifier["next_action"]
    assert "CWL_GRC_EVIDENCE_KEY" in missing_verifier["next_action"]


def test_invalid_keyverse_flag_fails_closed_instead_of_header_preview(
    monkeypatch, capsys
) -> None:  # noqa: ANN001
    """A misspelled hardened-start flag must not boot the unauthenticated preview."""
    from cwl_grc.cli import serve_http

    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "treu")
    with pytest.raises(ValueError, match="CWL_GRC_REQUIRE_KEYVERSE must be"):
        keyverse_start_is_required()
    assert serve_http() == 2
    payload = json.loads(capsys.readouterr().out)
    assert "CWL_GRC_REQUIRE_KEYVERSE" in payload["error"]
    assert "0, false, no, or unset" in payload["next_action"]


def test_invalid_port_fails_closed_with_numeric_port_next_action(
    monkeypatch, capsys
) -> None:  # noqa: ANN001
    """A non-numeric PORT must not start the preview or hide the remediation."""
    from cwl_grc.cli import serve_http

    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    monkeypatch.setenv("PORT", "abc")
    assert serve_http() == 2
    payload = json.loads(capsys.readouterr().out)
    assert "PORT" in payload["error"]
    assert "numeric PORT" in payload["next_action"]


def test_preview_startup_error_mentions_evidence_key_not_keyverse(
    monkeypatch, capsys, tmp_path
) -> None:  # noqa: ANN001
    """Ordinary preview failures must not tell officers to inject Keyverse TLS."""
    from cwl_grc.cli import serve_http

    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    monkeypatch.delenv("CWL_GRC_EVIDENCE_KEY", raising=False)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", f"sqlite:///{tmp_path / 'grc.sqlite'}")
    assert serve_http() == 2
    payload = json.loads(capsys.readouterr().out)
    assert "CWL_GRC_EVIDENCE_KEY" in payload["error"]
    assert "CWL_GRC_EVIDENCE_KEY" in payload["next_action"]
    assert "TLS" not in payload["next_action"]


def _write_reviewed_jwks(tmp_path) -> Path:  # noqa: ANN001
    """Write one reviewed public JWK set used by the hardened local start."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    path = tmp_path / "keyverse.jwks.json"
    path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    return path


def test_process_access_token_verifier_loads_reviewed_jwks(
    monkeypatch, tmp_path
) -> None:  # noqa: ANN001
    """A hardened CLI start injects the offline JWKS verifier instead of headers."""
    from cwl_grc.cli import serve_http
    from cwl_grc.keyverse_http import process_access_token_verifier

    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    assert process_access_token_verifier() is None

    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "1")
    cert, key = _write_tls_files(tmp_path)
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    monkeypatch.setenv("CWL_GRC_KEYVERSE_ISSUER", "https://identity.example.test/realms/cwl")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_AUDIENCE", "cwl-grc-api")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_CLIENT_IDS", "cwl-grc-web")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_JWKS_PATH", str(tmp_path / "missing.jwks"))
    with pytest.raises(ValueError, match="readable file"):
        process_access_token_verifier()

    empty = tmp_path / "empty.jwks.json"
    empty.write_text('{"keys": []}', encoding="utf-8")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_JWKS_PATH", str(empty))
    with pytest.raises(ValueError, match="public keys"):
        process_access_token_verifier()

    jwks = _write_reviewed_jwks(tmp_path)
    monkeypatch.setenv("CWL_GRC_KEYVERSE_JWKS_PATH", str(jwks))
    verifier = process_access_token_verifier()
    assert verifier is not None
    assert verifier.issuer == "https://identity.example.test/realms/cwl"

    captured: dict[str, object] = {}

    def fake_run(app, **kwargs):  # noqa: ANN001
        captured["verifier"] = app.state.access_token_verifier is not None
        captured["ssl"] = "ssl_certfile" in kwargs

    monkeypatch.setattr("cwl_grc.cli.uvicorn.run", fake_run)
    monkeypatch.setenv(
        "CWL_GRC_EVIDENCE_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    assert serve_http() == 0
    assert captured == {"verifier": True, "ssl": True}


def test_hardened_start_missing_evidence_key_names_key_in_next_action(
    monkeypatch, capsys, tmp_path
) -> None:  # noqa: ANN001
    """A hardened persistent start states the evidence key, not only Keyverse TLS."""
    from cwl_grc.cli import serve_http

    cert, key = _write_tls_files(tmp_path)
    jwks = _write_reviewed_jwks(tmp_path)
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "1")
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    monkeypatch.setenv("CWL_GRC_KEYVERSE_ISSUER", "https://identity.example.test/realms/cwl")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_AUDIENCE", "cwl-grc-api")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_CLIENT_IDS", "cwl-grc-web")
    monkeypatch.setenv("CWL_GRC_KEYVERSE_JWKS_PATH", str(jwks))
    monkeypatch.delenv("CWL_GRC_EVIDENCE_KEY", raising=False)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", f"sqlite:///{tmp_path / 'grc.sqlite'}")
    assert serve_http() == 2
    payload = json.loads(capsys.readouterr().out)
    assert "CWL_GRC_EVIDENCE_KEY" in payload["error"]
    assert "CWL_GRC_EVIDENCE_KEY" in payload["next_action"]
    assert "CWL_GRC_TLS_CERTFILE" in payload["next_action"]
