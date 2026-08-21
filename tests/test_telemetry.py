"""OpenTelemetry traces, metrics, and cardinality contracts."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from opentelemetry.trace import StatusCode
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import cwl_grc.telemetry as telemetry_module
from cwl_grc import create_app
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
    span_exporter = InMemorySpanExporter()
    app.state.telemetry._tracer_provider.add_span_processor(
        SimpleSpanProcessor(span_exporter)
    )
    valid_traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"traceparent": valid_traceparent})
        denied = client.post(
            "/evidence-records/record-with-secret-id/legal-hold",
            headers={"X-Actor-Id": "officer", "X-Purpose": "wrong"},
            json={"hold_reason": "reason", "hold_authority": "authority"},
        )
        metrics = _metrics(app)

    assert response.status_code == 200
    assert denied.status_code == 403
    server_span = span_exporter.get_finished_spans()[0]
    traceparent_parts = response.headers["traceparent"].split("-")
    assert traceparent_parts[1] == f"{server_span.context.trace_id:032x}"
    assert traceparent_parts[2] == f"{server_span.context.span_id:016x}"
    assert {"http.server.request.count", "http.server.request.duration"}.issubset(metrics)
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
    assert all("record-with-secret-id" not in point.attributes.values() for point in request_points)


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
        with telemetry.server_span("GET", "/healthz", {}) as span:
            raise RuntimeError("telemetry failure")
    assert span.status.status_code is StatusCode.ERROR
    assert span.events == ()
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
def test_request_log_traceparent_matches_response_span(caplog) -> None:
    """Keep the structured request log correlated with the emitted server span."""
    import json

    from fastapi.testclient import TestClient

    from cwl_grc.app import create_app

    with TestClient(create_app(database_url="sqlite://", evidence_key=None)) as client:
        with caplog.at_level("INFO", logger="cwl_grc.request"):
            response = client.get("/healthz")

    record = next(record for record in reversed(caplog.records) if record.name == "cwl_grc.request")
    assert json.loads(record.message)["traceparent"] == response.headers["traceparent"]
