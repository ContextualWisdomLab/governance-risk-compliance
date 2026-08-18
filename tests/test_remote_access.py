"""Regression tests for the fail-closed developer-preview network boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.remote_access import remote_preview_enabled, request_is_local


def test_remote_preview_flag_is_explicit(monkeypatch) -> None:  # noqa: ANN001
    """Remote preview stays disabled unless the operator explicitly opts in."""
    monkeypatch.delenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", raising=False)
    assert remote_preview_enabled() is False
    monkeypatch.setenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", " TrUe ")
    assert remote_preview_enabled() is True
    monkeypatch.setenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", "no")
    assert remote_preview_enabled() is False


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


def test_forwarded_remote_preview_is_denied_by_default(monkeypatch) -> None:  # noqa: ANN001
    """A proxy-forwarded request cannot reach the unauthenticated preview by default."""
    monkeypatch.delenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", raising=False)
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))

    local = client.get("/healthz")
    remote = client.get("/healthz", headers={"X-Forwarded-For": "198.51.100.23"})

    assert local.status_code == 200
    assert remote.status_code == 503
    assert remote.json() == {
        "detail": (
            "Remote preview is disabled. Configure Keyverse-backed identity and tenant "
            "authorization before exposing CWL GRC."
        )
    }


def test_remote_preview_opt_in_is_explicitly_unsafe(monkeypatch) -> None:  # noqa: ANN001
    """The documented escape hatch is deliberate and does not masquerade as authentication."""
    monkeypatch.setenv("CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW", "1")
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))

    response = client.get("/healthz", headers={"Forwarded": "for=198.51.100.23"})

    assert response.status_code == 200
