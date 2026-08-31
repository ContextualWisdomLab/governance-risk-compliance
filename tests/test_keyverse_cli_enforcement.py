"""Officer CLI mutations consume Keyverse tokens instead of --actor identity."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from cwl_grc.catalog import FrameworkCode
from cwl_grc.cli import main as cli_main


ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
EVIDENCE_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _write_tls_files(tmp_path: Path) -> tuple[Path, Path]:
    """Write readable TLS path placeholders used by the hardened local start."""
    cert = tmp_path / "grc.crt"
    key = tmp_path / "grc.key"
    cert.write_text("certificate", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    return cert, key


def _signing_material() -> tuple[Any, dict[str, Any]]:
    """Return one RSA key pair as a public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _write_jwks(tmp_path: Path, public_jwk: dict[str, Any]) -> Path:
    """Write one reviewed public JWK set."""
    path = tmp_path / "keyverse.jwks.json"
    path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    return path


def _token(private_key: Any, **overrides: Any) -> str:
    """Sign one RFC 9068 access token for the GRC resource audience."""
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "officer-park",
        "aud": AUDIENCE,
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "nbf": int((now - timedelta(seconds=5)).timestamp()),
        "iat": int((now - timedelta(seconds=5)).timestamp()),
        "jti": "token-park-cli-01",
        "client_id": CLIENT_ID,
        "scope": "openid grc.policy.read grc.policy.write grc.evidence.write",
        "role": "compliance_officer",
        "org": "tenant-acme",
        "workspace": "grc-primary",
        "principal_kind": "human",
    }
    claims.update(overrides)
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1", "typ": "at+jwt"},
    )


def _harden(monkeypatch, tmp_path: Path, public_jwk: dict[str, Any]) -> None:  # noqa: ANN001
    """Configure a Keyverse-required CLI process against one reviewed JWKS file."""
    cert, key = _write_tls_files(tmp_path)
    jwks = _write_jwks(tmp_path, public_jwk)
    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "1")
    monkeypatch.setenv("CWL_GRC_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("CWL_GRC_TLS_KEYFILE", str(key))
    monkeypatch.setenv("CWL_GRC_KEYVERSE_ISSUER", ISSUER)
    monkeypatch.setenv("CWL_GRC_KEYVERSE_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("CWL_GRC_KEYVERSE_CLIENT_IDS", CLIENT_ID)
    monkeypatch.setenv("CWL_GRC_KEYVERSE_JWKS_PATH", str(jwks))
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEY", EVIDENCE_KEY)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", f"sqlite:///{tmp_path / 'grc.sqlite'}")


def test_hardened_cli_author_refuses_declared_actor_without_token(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """CWL_GRC_REQUIRE_KEYVERSE blocks --actor policy writes without a Bearer token."""
    private_key, public_jwk = _signing_material()
    del private_key
    _harden(monkeypatch, tmp_path, public_jwk)
    monkeypatch.delenv("CWL_GRC_ACCESS_TOKEN", raising=False)
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Logical Access Policy",
                "--body",
                "Least privilege for CSAP 10.2.1.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-park",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status_code"] == 401
    assert "Keyverse access token" in payload["error"]
    assert "CWL_GRC_ACCESS_TOKEN" in payload["next_action"]
    assert "CSAP 10.2.1" in payload["next_action"]


def test_hardened_cli_rejects_actor_impersonation(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """--actor cannot impersonate a verified Keyverse subject on CLI writes."""
    private_key, public_jwk = _signing_material()
    _harden(monkeypatch, tmp_path, public_jwk)
    monkeypatch.setenv("CWL_GRC_ACCESS_TOKEN", _token(private_key))
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Logical Access Policy",
                "--body",
                "Least privilege for CSAP 10.2.1.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-impostor",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status_code"] == 401
    assert "impersonate" in payload["error"]
    assert "CWL_GRC_ACCESS_TOKEN" in payload["next_action"]
    listed_status = cli_main(["policy", "list"])
    listed = json.loads(capsys.readouterr().out)
    assert listed_status == 0
    assert listed["policies"] == []


def test_hardened_cli_authors_binds_and_lists_with_verified_tenant(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """A Keyverse CLI token stamps tenant ownership and hides another organization's gaps."""
    private_key, public_jwk = _signing_material()
    _harden(monkeypatch, tmp_path, public_jwk)
    park = _token(private_key)
    beta = _token(
        private_key,
        sub="officer-lee",
        org="tenant-beta",
        jti="token-lee-cli-01",
    )
    monkeypatch.setenv("CWL_GRC_ACCESS_TOKEN", park)
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Logical Access Policy",
                "--body",
                "Least privilege for CSAP 10.2.1.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-park",
            ]
        )
        == 0
    )
    authored = json.loads(capsys.readouterr().out)
    assert authored["next_action"] == "Review policy gaps and attach the next evidence."
    assert "CWL_GRC_ACCESS_TOKEN" not in json.dumps(authored)
    monkeypatch.setenv("CWL_GRC_ACCESS_TOKEN", beta)
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Beta Access Policy",
                "--body",
                "Tenant-beta maps CSAP 10.2.1 without closing tenant-acme.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-lee",
            ]
        )
        == 0
    )
    beta_policy = json.loads(capsys.readouterr().out)
    monkeypatch.setenv("CWL_GRC_ACCESS_TOKEN", park)
    assert cli_main(["policy", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    titles = {item["policy_title"] for item in listed["policies"]}
    assert titles == {"Logical Access Policy"}
    assert (
        cli_main(
            [
                "bind",
                "--framework",
                FrameworkCode.CSAP_2026.value,
                "--identifier",
                "10.2.1",
                "--title",
                "CSAP 10.2.1 register",
                "--payload",
                "park@example.co.kr approved the grant register.",
                "--actor",
                "officer-park",
            ]
        )
        == 0
    )
    bound = json.loads(capsys.readouterr().out)
    assert "park@example.co.kr" in json.dumps(bound)
    assert cli_main(["gaps"]) == 0
    park_gaps = json.loads(capsys.readouterr().out)
    assert park_gaps["gaps"] == []
    monkeypatch.setenv("CWL_GRC_ACCESS_TOKEN", beta)
    assert cli_main(["gaps"]) == 0
    beta_gaps = json.loads(capsys.readouterr().out)
    assert {item["catalog_identifier"] for item in beta_gaps["gaps"]} == {"10.2.1"}
    assert beta_gaps["gaps"][0]["policy_document_id"] == beta_policy["policy_document_id"]


def test_hardened_cli_list_requires_token(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """Policy list and gaps cannot dump tenant records under a hardened start."""
    private_key, public_jwk = _signing_material()
    del private_key
    _harden(monkeypatch, tmp_path, public_jwk)
    monkeypatch.delenv("CWL_GRC_ACCESS_TOKEN", raising=False)
    assert cli_main(["policy", "list"]) == 1
    listed = json.loads(capsys.readouterr().out)
    assert listed["status_code"] == 401
    assert "CWL_GRC_ACCESS_TOKEN" in listed["next_action"]
    assert cli_main(["gaps"]) == 1
    gaps = json.loads(capsys.readouterr().out)
    assert gaps["status_code"] == 401
    assert "CWL_GRC_ACCESS_TOKEN" in gaps["next_action"]


def test_invalid_keyverse_flag_blocks_cli_actor_writes(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """A misspelled hardened flag must not fall back to --actor policy writes."""
    from fastapi import HTTPException

    from cwl_grc.authorization import PurposeCode
    from cwl_grc.cli import _cli_decision, _cli_http_next_action
    from cwl_grc.keyverse_http import POLICY_WRITE_SCOPES

    monkeypatch.setenv("CWL_GRC_REQUIRE_KEYVERSE", "treu")
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEY", EVIDENCE_KEY)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", f"sqlite:///{tmp_path / 'grc.sqlite'}")
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Logical Access Policy",
                "--body",
                "Least privilege for CSAP 10.2.1.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-park",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert "CWL_GRC_REQUIRE_KEYVERSE" in payload["error"]
    assert "CWL_GRC_ACCESS_TOKEN" in payload["next_action"]
    guidance = _cli_http_next_action(HTTPException(status_code=401, detail="denied"))
    assert "CWL_GRC_ACCESS_TOKEN" in guidance
    monkeypatch.delenv("CWL_GRC_REQUIRE_KEYVERSE", raising=False)
    try:
        _cli_decision(None, PurposeCode.POLICY_AUTHORING, POLICY_WRITE_SCOPES)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:  # pragma: no cover
        raise AssertionError("preview CLI writes must still require --actor")


def test_hardened_cli_write_requires_policy_write_scope(
    monkeypatch, tmp_path, capsys
) -> None:  # noqa: ANN001
    """A verified token without grc.policy.write cannot author through the CLI."""
    private_key, public_jwk = _signing_material()
    _harden(monkeypatch, tmp_path, public_jwk)
    monkeypatch.setenv(
        "CWL_GRC_ACCESS_TOKEN",
        _token(private_key, scope="openid grc.policy.read"),
    )
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Logical Access Policy",
                "--body",
                "Least privilege for CSAP 10.2.1.",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                "--actor",
                "officer-park",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status_code"] == 403
    assert "CWL_GRC_ACCESS_TOKEN" in payload["next_action"]
