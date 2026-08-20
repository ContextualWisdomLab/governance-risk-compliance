"""Regression tests for the fail-closed developer-preview network boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.remote_access import request_is_local


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
        assert response.json()["detail"] == (
            "Remote preview is disabled. Configure Keyverse-backed identity and "
            "tenant authorization before exposing CWL GRC."
        )
        assert response.json()["request_reference"] == response.headers["X-Request-ID"]
