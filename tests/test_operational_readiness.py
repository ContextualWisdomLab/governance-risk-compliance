"""Operational probe, drain, correlation, and redaction contracts."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

import cwl_grc.database as database_module
from cwl_grc import create_app
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.health import (
    LOCAL_PREVIEW_ENVIRONMENT,
    LifecycleState,
    _guard_names,
    _identity_check,
    _evidence_key_check,
    readiness_payload,
)
from cwl_grc.observability import (
    build_request_context,
    emit_request_log,
    principal_reference,
    reset_request_state,
    reset_verified_principal,
    set_request_state,
    set_verified_principal,
)


def _app() -> Any:
    """Build an isolated local-preview app with an explicitly ephemeral key."""
    return create_app(database_url="sqlite://", evidence_key=None)


def test_health_readiness_startup_and_trace_contracts() -> None:
    """Healthy local preview exposes distinct truthful probe contracts."""
    app = _app()
    client = TestClient(app)
    health = client.get("/healthz")
    ready = client.get("/readyz")
    startup = client.get("/startupz")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "cwl-grc"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert all(check["status"] == "ok" for check in ready.json()["checks"].values())
    assert startup.json()["status"] == "started"
    assert startup.json()["checks"] == app.state.startup_report["checks"]
    assert ready.headers["X-Request-ID"]
    assert ready.headers["traceparent"].startswith("00-")


def test_correlation_headers_are_preserved_or_replaced() -> None:
    """Request IDs survive while server spans continue or replace trace context."""
    app = _app()
    client = TestClient(app)
    valid_request_id = "officer-request:2026-08-20"
    valid_traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    preserved = client.get(
        "/healthz",
        headers={"X-Request-ID": valid_request_id, "traceparent": valid_traceparent},
    )
    assert preserved.headers["X-Request-ID"] == valid_request_id
    returned_traceparent = preserved.headers["traceparent"].split("-")
    assert returned_traceparent[0] == "00"
    assert returned_traceparent[1] == valid_traceparent.split("-")[1]
    assert returned_traceparent[2] != valid_traceparent.split("-")[2]

    replaced = client.get(
        "/healthz",
        headers={"X-Request-ID": "bad request", "traceparent": "00-" + "0" * 48 + "-01"},
    )
    assert replaced.headers["X-Request-ID"] != "bad request"
    assert replaced.headers["traceparent"] != "00-" + "0" * 48 + "-01"

    assert build_request_context(None, None).request_id
    assert build_request_context("", "ff-0123456789abcdef0123456789abcdef-0123456789abcdef-01")


def test_error_references_are_safe_and_validation_body_is_not_echoed() -> None:
    """HTTP failures return a correlation reference without echoing evidence input."""
    client = TestClient(_app())
    denied = client.post(
        "/evidence-records",
        headers={"X-Request-ID": "denied-request", "X-Actor-Id": "officer", "X-Purpose": "wrong"},
        json={"evidence_title": "secret evidence", "payload_text": "secret plaintext"},
    )
    assert denied.status_code == 403
    assert denied.json()["request_reference"] == "denied-request"
    assert "secret plaintext" not in denied.text

    invalid = client.post("/officer/policy", data={"policy_body": "secret plaintext"})
    assert invalid.status_code == 422
    assert invalid.json()["request_reference"]
    assert "secret plaintext" not in invalid.text


def test_router_errors_preserve_request_reference_and_exception_headers() -> None:
    """Router and Starlette errors use the same safe correlation response contract."""
    app = _app()

    def throttled() -> None:
        """Raise a router-compatible error with a retry instruction."""
        raise StarletteHTTPException(status_code=429, detail="retry", headers={"Retry-After": "3"})

    app.add_api_route("/test-throttled", throttled)
    client = TestClient(app, raise_server_exceptions=False)

    missing = client.get("/not-registered", headers={"X-Request-ID": "missing-route"})
    assert missing.status_code == 404
    assert missing.json()["request_reference"] == "missing-route"
    assert missing.headers["X-Request-ID"] == "missing-route"

    limited = client.get("/test-throttled", headers={"X-Request-ID": "limited-route"})
    assert limited.status_code == 429
    assert limited.json()["request_reference"] == "limited-route"
    assert limited.headers["Retry-After"] == "3"
    assert limited.headers["X-Request-ID"] == "limited-route"


def test_drain_preserves_liveness_and_rejects_new_mutations() -> None:
    """A draining instance stays alive, becomes unready, and rejects new writes."""
    app = _app()
    app.state.lifecycle.begin_drain()
    client = TestClient(app)

    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["checks"]["lifecycle"]["reason_code"] == "draining"
    mutation = client.post(
        "/evidence-records",
        headers={"X-Actor-Id": "officer", "X-Purpose": "evidence_binding"},
        json={"evidence_title": "Evidence", "payload_text": "Exact text"},
    )
    assert mutation.status_code == 503
    assert mutation.json()["request_reference"] == mutation.headers["X-Request-ID"]

    state = LifecycleState("draining")
    state.mark_ready()
    assert state.state == "draining"


def test_readiness_reports_schema_receipt_seed_guard_and_key_failures() -> None:
    """Readiness returns reason codes for each dependency failure without leaking details."""
    for mutation in (
        "DELETE FROM schema_migration WHERE migration_key = '0004_evidence_retention'",
        "DELETE FROM control_item",
        "DROP TRIGGER audit_event_block_update",
    ):
        app = _app()
        with app.state.session_factory.kw["bind"].begin() as connection:
            connection.execute(text(mutation))
        report = readiness_payload(
            app.state.session_factory,
            app.state.evidence_cipher,
            LOCAL_PREVIEW_ENVIRONMENT,
            None,
            app.state.lifecycle,
        )
        assert report["status"] == "not_ready"
        assert any(check["status"] == "fail" for check in report["checks"].values())

    app = _app()
    app.state.session_factory.kw["bind"].dispose()
    broken = TestClient(app).get("/readyz")
    assert broken.status_code == 503
    assert broken.json()["checks"]["schema"]["reason_code"] == "schema_incompatible"

    key_failure = _evidence_key_check(type("BrokenCipher", (), {
        "encrypt_record": lambda _self, _value, context: (_ for _ in ()).throw(RuntimeError()),
    })())
    assert key_failure["reason_code"] == "evidence_key_unavailable"

    class BrokenFactory:
        """Fail before a database session can be opened."""

        def __call__(self) -> Any:
            """Raise the simulated database outage."""
            raise RuntimeError("database offline")

    database_failure = readiness_payload(
        BrokenFactory(),
        EvidenceCipher(None, allow_ephemeral=True),
        LOCAL_PREVIEW_ENVIRONMENT,
        None,
    )
    assert database_failure["checks"]["database"]["reason_code"] == "database_unreachable"

    class WrongRoundTripCipher:
        """Return a valid-shaped but incorrect readiness round trip."""

        def encrypt_record(self, value: str, *, context: str) -> object:
            """Return a placeholder encrypted value."""
            return object()

        def decrypt_record(self, encrypted: object, *, context: str) -> str:
            """Return the wrong plaintext to exercise integrity failure handling."""
            return "wrong-readiness-value"

    assert _evidence_key_check(WrongRoundTripCipher())["reason_code"] == (
        "evidence_key_round_trip_failed"
    )


def test_readiness_rejects_missing_required_purpose_with_matching_row_count() -> None:
    """Readiness verifies required purpose identifiers, not only their row count."""
    app = _app()
    with app.state.session_factory.kw["bind"].begin() as connection:
        connection.execute(
            text(
                "DELETE FROM authorization_purpose "
                "WHERE purpose_code = 'evidence_retention'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO authorization_purpose "
                "(purpose_code, purpose_label, purpose_description) "
                "VALUES ('unsupported', 'Unsupported', 'Unsupported')"
            )
        )

    report = readiness_payload(
        app.state.session_factory,
        app.state.evidence_cipher,
        LOCAL_PREVIEW_ENVIRONMENT,
        None,
        app.state.lifecycle,
    )
    assert report["status"] == "not_ready"
    assert report["checks"]["seed_state"]["reason_code"] == "seed_state_incomplete"


def test_startup_rejects_production_preview_and_unknown_environment(monkeypatch) -> None:  # noqa: ANN001
    """Production cannot start behind the local-only boundary or unknown environment."""
    monkeypatch.setenv("CWL_GRC_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="keyverse_configuration_required"):
        create_app(database_url="sqlite://", evidence_key=None)

    monkeypatch.delenv("CWL_GRC_ENVIRONMENT")
    app = _app()
    unsupported = readiness_payload(
        app.state.session_factory,
        app.state.evidence_cipher,
        "staging",
        object(),
    )
    assert unsupported["checks"]["identity_configuration"]["reason_code"] == (
        "unsupported_environment"
    )
    assert _identity_check("production", object())["reason_code"] == (
        "remote_access_boundary_disabled"
    )
    assert readiness_payload(
        app.state.session_factory,
        app.state.evidence_cipher,
        LOCAL_PREVIEW_ENVIRONMENT,
        None,
        LifecycleState(),
    )["checks"]["lifecycle"]["reason_code"] == "startup_incomplete"


def test_structured_logs_hash_principals_and_handle_uncaught_errors(caplog) -> None:  # noqa: ANN001
    """Request logs are JSON, correlated, and free of raw principal or payload values."""
    caplog.set_level(logging.INFO, logger="cwl_grc.request")
    token = set_verified_principal("tenant-secret", "actor-secret")
    try:
        assert principal_reference() is not None
        context = build_request_context("log-request", None)
        emit_request_log(context, "GET", "/healthz", 200, 1.25, LOCAL_PREVIEW_ENVIRONMENT)
    finally:
        reset_verified_principal(token)
    record = json.loads(caplog.records[-1].message)
    assert record["request_id"] == "log-request"
    assert record["principal_reference"] != "tenant-secret"
    assert "actor-secret" not in caplog.text

    emit_request_log(context, "GET", "/healthz", 500, 1.25, LOCAL_PREVIEW_ENVIRONMENT)
    error_record = json.loads(caplog.records[-1].message)
    assert error_record["severity"] == "ERROR"
    assert caplog.records[-1].levelno == logging.ERROR

    app = _app()

    def explode() -> None:
        """Raise one controlled test-only exception."""
        raise RuntimeError("secret plaintext")

    app.add_api_route("/test-explode", explode)
    response = TestClient(app, raise_server_exceptions=False).get("/test-explode")
    assert response.status_code == 500
    assert "secret plaintext" not in caplog.text


def test_request_state_preserves_authenticated_principal_across_worker_boundary() -> None:
    """A shared ASGI state object carries verified identity into request logging."""
    state: dict[str, Any] = {}
    state_token = set_request_state(state)
    principal_token = set_verified_principal("tenant-secret", "actor-secret")
    try:
        assert principal_reference() is not None
        assert state["verified_principal"] == ("tenant-secret", "actor-secret")
    finally:
        reset_verified_principal(principal_token)
        reset_request_state(state_token)


def test_postgresql_engine_timeout_and_invalid_timeout(monkeypatch) -> None:  # noqa: ANN001
    """PostgreSQL connections receive a finite connect timeout and reject invalid values."""
    captured: dict[str, Any] = {}

    def fake_create_engine(url: str, **kwargs: Any) -> object:
        """Capture engine construction without requiring a PostgreSQL driver."""
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database_module, "create_engine", fake_create_engine)
    database_module.build_engine("postgresql+psycopg://db", connect_timeout_seconds=4)
    assert captured["kwargs"] == {"connect_args": {"connect_timeout": 4}}
    with pytest.raises(ValueError, match="positive integer"):
        database_module.build_engine("sqlite://", connect_timeout_seconds=0)
    with pytest.raises(ValueError, match="positive integer"):
        database_module.build_engine("sqlite://", connect_timeout_seconds=True)


def test_postgresql_guard_query_shape() -> None:
    """The PostgreSQL guard query is selected without exposing table contents."""
    class Dialect:
        """Provide the dialect marker needed by the guard query."""

        name = "postgresql"

    class Bound:
        """Provide the SQLAlchemy bind marker needed by the guard query."""

        dialect = Dialect()

    class Result:
        """Return deterministic trigger names from the test query."""

        def scalars(self) -> list[str]:
            """Return one PostgreSQL guard name."""
            return ["audit_event_immutable"]

    class SessionStub:
        """Record the PostgreSQL trigger query without a live server."""

        bind = Bound()

        def execute(self, statement: object) -> Result:
            """Return the deterministic trigger result."""
            assert "pg_trigger" in str(statement)
            return Result()

    assert _guard_names(SessionStub()) == {"audit_event_immutable"}
