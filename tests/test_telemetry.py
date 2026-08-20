"""OpenTelemetry traces, metrics, and cardinality contracts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import cwl_grc.telemetry as telemetry_module
from cwl_grc import database as database_module
from cwl_grc import create_app
from cwl_grc.database import session_dependency
from cwl_grc.observability import route_template
from cwl_grc.telemetry import (
    OTEL_ENDPOINT_ENVIRONMENT_VARIABLE,
    RequestTelemetry,
)


def _app():
    """Build an isolated app for telemetry integration evidence."""
    return create_app(database_url="sqlite://", evidence_key=None)


def _metrics(app) -> dict[str, object]:  # noqa: ANN001
    """Flatten the in-memory reader to metric names for assertions."""
    data = app.state.telemetry.metric_reader.get_metrics_data()
    return {
        metric.name: metric
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


def test_requests_emit_otel_metrics_with_route_templates_and_spans() -> None:
    """Requests emit standard rate/duration metrics without raw path identifiers."""
    app = _app()
    valid_traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"traceparent": valid_traceparent})
        created = client.post(
            "/evidence-records",
            headers={"X-Actor-Id": "officer", "X-Purpose": "evidence_binding"},
            json={"evidence_title": "title", "payload_text": "payload"},
        )
        denied = client.post(
            "/evidence-records/record-with-secret-id/legal-hold",
            headers={"X-Actor-Id": "officer", "X-Purpose": "wrong"},
            json={"hold_reason": "reason", "hold_authority": "authority"},
        )
        metrics = _metrics(app)

    assert response.status_code == 200
    assert created.status_code == 201
    assert denied.status_code == 403
    assert {
        "http.server.request.count",
        "http.server.request.duration",
        "cwl_grc.database.transaction.count",
        "cwl_grc.database.transaction.duration",
        "cwl_grc.audit.write.count",
    }.issubset(metrics)
    request_points = metrics["http.server.request.count"].data.data_points  # type: ignore[attr-defined]
    assert any(
        point.attributes["http.route"] == "/healthz"
        and point.attributes["http.response.status_code"] == 200
        for point in request_points
    )
    denial_points = metrics["cwl_grc.authorization.denial.count"].data.data_points  # type: ignore[attr-defined]
    assert any(
        point.attributes["http.route"] == "/evidence-records/{evidence_record_id}/legal-hold"
        for point in denial_points
    )
    audit_points = metrics["cwl_grc.audit.write.count"].data.data_points  # type: ignore[attr-defined]
    assert any(
        point.attributes["cwl_grc.outcome"] == "success" and point.value == 1
        for point in audit_points
    )
    assert all("record-with-secret-id" not in point.attributes.values() for point in request_points)


def test_session_dependency_supports_uninstrumented_callers() -> None:
    """The database helper remains usable for callers without telemetry state."""
    app = _app()
    dependency = session_dependency(app.state.session_factory)
    next(dependency)
    with pytest.raises(StopIteration):
        next(dependency)


def test_database_pool_metrics_use_bounded_database_labels(tmp_path: Path) -> None:
    """A durable SQLite QueuePool emits bounded pool observations."""
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'pool.sqlite'}",
        evidence_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        metrics = _metrics(app)

    for name in (
        "cwl_grc.database.pool.size",
        "cwl_grc.database.pool.checked_out",
        "cwl_grc.database.pool.checked_in",
        "cwl_grc.database.pool.overflow",
    ):
        points = metrics[name].data.data_points  # type: ignore[attr-defined]
        assert points
        assert {point.attributes["db.system.name"] for point in points} == {"sqlite"}


def test_recovery_event_metrics_use_bounded_modes_and_outcomes() -> None:
    """Recovery telemetry accepts only the documented bounded contract."""
    app = _app()
    telemetry = app.state.telemetry
    telemetry.record_recovery_event("replacement", "success", 12.5)
    metrics = _metrics(app)

    count_points = metrics["cwl_grc.recovery.event.count"].data.data_points  # type: ignore[attr-defined]
    duration_points = metrics["cwl_grc.recovery.duration"].data.data_points  # type: ignore[attr-defined]
    assert count_points[0].value == 1
    assert count_points[0].attributes == {
        "cwl_grc.recovery.mode": "replacement",
        "cwl_grc.outcome": "success",
    }
    assert duration_points[0].sum == 12.5
    with pytest.raises(ValueError, match="Recovery mode"):
        telemetry.record_recovery_event("unknown", "success", 1.0)
    with pytest.raises(ValueError, match="Recovery outcome"):
        telemetry.record_recovery_event("read_only", "unknown", 1.0)


def test_session_dependency_records_failed_audit_commit() -> None:
    """A failed transaction records audit failure without changing rollback behavior."""
    class Dialect:
        """Provide the bounded database-system label."""

        name = "sqlite"

    class Bind:
        """Provide the dialect used by the fake session."""

        dialect = Dialect()

    class FailingSession:
        """Fail commit after one pending audit event."""

        bind = Bind()
        info = {database_module.AUDIT_EVENT_COUNT_INFO_KEY: 1}

        def commit(self) -> None:
            """Raise the simulated database failure."""
            raise RuntimeError("commit failed")

        def rollback(self) -> None:
            """Accept the required rollback."""

        def close(self) -> None:
            """Accept the required close."""

    class Telemetry:
        """Capture transaction and audit failure measurements."""

        def __init__(self) -> None:
            self.transaction = None
            self.audit = None

        def record_database_transaction(self, *values) -> None:  # noqa: ANN002
            """Capture the transaction measurement."""
            self.transaction = values

        def record_audit_write(self, *values) -> None:  # noqa: ANN002
            """Capture the audit measurement."""
            self.audit = values

    telemetry = Telemetry()
    dependency = database_module.session_dependency(lambda: FailingSession(), telemetry)
    next(dependency)
    with pytest.raises(RuntimeError, match="commit failed"):
        next(dependency)
    assert telemetry.transaction[1] == "rollback"
    assert telemetry.audit[1:] == ("failure", 1)


def test_telemetry_exception_and_otlp_exporter_configuration(monkeypatch) -> None:  # noqa: ANN001
    """The SDK records failures and uses the standard OTLP endpoint switch."""
    monkeypatch.setenv(OTEL_ENDPOINT_ENVIRONMENT_VARIABLE, "http://127.0.0.1:4318")
    metric_exporter = Mock()
    metric_exporter._preferred_temporality = {}
    metric_exporter._preferred_aggregation = {}
    span_exporter = Mock()
    monkeypatch.setattr(telemetry_module, "OTLPMetricExporter", lambda: metric_exporter)
    monkeypatch.setattr(telemetry_module, "OTLPSpanExporter", lambda: span_exporter)
    telemetry = RequestTelemetry("local_preview")
    with pytest.raises(RuntimeError, match="telemetry failure"):
        with telemetry.server_span("GET", "/healthz", {}):
            raise RuntimeError("telemetry failure")
    assert telemetry.metric_reader.get_metrics_data() is None
    telemetry.record_request("GET", "/healthz", 403, 0.01)
    telemetry.shutdown()
    assert metric_exporter.shutdown.called
    assert span_exporter.shutdown.called


def test_route_template_rejects_unmatched_raw_paths() -> None:
    """Unmatched requests use a stable label instead of logging raw identifiers."""
    assert route_template({}) == "unmatched"

    class Route:
        """Provide a registered route path for the template helper."""

        path = "/evidence-records/{evidence_record_id}"

    assert route_template({"route": Route()}) == "/evidence-records/{evidence_record_id}"
