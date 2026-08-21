"""OpenTelemetry traces, metrics, and redaction contracts for GRC requests."""

from __future__ import annotations

import json
import logging
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import cwl_grc.telemetry as telemetry_module
from cwl_grc import create_app
from cwl_grc.observability import (
    build_request_context,
    emit_request_log,
    principal_reference,
    reset_verified_principal,
    route_template,
    set_verified_principal,
)
from cwl_grc.telemetry import OTEL_ENDPOINT_ENVIRONMENT_VARIABLE, RequestTelemetry


def _app():
    """Build an isolated in-memory app with the real telemetry boundary."""
    return create_app(database_url="sqlite://", evidence_key=None)


def _metrics(app) -> dict[str, object]:  # noqa: ANN001
    """Flatten the in-memory SDK reader by metric name."""
    data = app.state.telemetry.metric_reader.get_metrics_data()
    return {
        metric.name: metric
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


def test_requests_emit_metrics_and_preserve_safe_correlation() -> None:
    """Requests emit bounded metrics and return validated correlation headers."""
    app = _app()
    traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    with TestClient(app) as client:
        response = client.get(
            "/healthz",
            headers={"X-Request-ID": "grc-smoke-1", "traceparent": traceparent},
        )
        denied = client.post(
            "/evidence-records",
            headers={"X-Actor-Id": "officer", "X-Purpose": "wrong"},
            json={"evidence_title": "secret title", "payload_text": "secret body"},
        )
        metrics = _metrics(app)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "grc-smoke-1"
    returned_traceparent = response.headers["traceparent"].split("-")
    assert returned_traceparent == traceparent.split("-")
    assert denied.status_code == 403
    assert {"http.server.request.count", "http.server.request.duration"}.issubset(metrics)
    request_points = metrics["http.server.request.count"].data.data_points  # type: ignore[attr-defined]
    assert any(
        point.attributes["http.route"] == "/healthz"
        and point.attributes["http.response.status_code"] == 200
        for point in request_points
    )
    denial_points = metrics["cwl_grc.authorization.denial.count"].data.data_points  # type: ignore[attr-defined]
    assert any(point.attributes["http.route"] == "/evidence-records" for point in denial_points)
    assert all("secret" not in str(point.attributes) for point in request_points)


def test_invalid_correlation_is_replaced() -> None:
    """Malformed request identifiers never become telemetry values."""
    context = build_request_context(
        "bad request",
        "00-" + "0" * 32 + "-" + "0" * 16 + "-01",
    )
    assert context.request_id != "bad request"
    assert context.traceparent != "00-" + "0" * 32 + "-" + "0" * 16 + "-01"
    assert build_request_context(None, None).request_id
    assert build_request_context(
        None,
        "ff-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    ).traceparent.startswith("00-")
    build_request_context(
        None,
        "00-0123456789abcdef0123456789abcdef-" + "0" * 16 + "-01",
    )


def test_logs_hash_principal_and_bound_error_fields(caplog: pytest.LogCaptureFixture) -> None:
    """Structured logs retain correlation while excluding raw tenant and actor values."""
    token = set_verified_principal("tenant-secret", "actor-secret")
    try:
        assert principal_reference() is not None
        caplog.set_level(logging.INFO, logger="cwl_grc.request")
        emit_request_log(
            build_request_context("request-1", None),
            "GET",
            "/healthz",
            500,
            1.25,
            "local_preview",
            "RuntimeError",
        )
    finally:
        reset_verified_principal(token)

    record = json.loads(caplog.records[-1].message)
    assert record["severity"] == "ERROR"
    assert record["error_class"] == "RuntimeError"
    assert "tenant-secret" not in caplog.text
    assert "actor-secret" not in caplog.text


def test_exporter_configuration_and_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured OTLP exporters are shut down and errors avoid exception events."""
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
    telemetry.record_request("GET", "/healthz", 403, 0.01)
    telemetry.shutdown()

    assert metric_exporter.shutdown.called
    assert span_exporter.shutdown.called


def test_route_template_uses_registered_path_only() -> None:
    """Unmatched requests use a stable label instead of a raw identifier."""
    assert route_template({}) == "unmatched"

    class Route:
        """Provide a registered route template for the helper."""

        path = "/evidence-records/{evidence_record_id}"

    assert route_template({"route": Route()}) == "/evidence-records/{evidence_record_id}"


def test_failed_request_logs_error_class_without_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected route failures expose a class and correlation, never exception text."""
    app = _app()

    def explode() -> None:
        """Raise a private message that must not cross the observability boundary."""
        raise RuntimeError("private evidence payload")

    app.add_api_route("/telemetry-failure", explode)
    caplog.set_level(logging.INFO, logger="cwl_grc.request")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/telemetry-failure",
        headers={"X-Request-ID": "failure-request"},
    )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-request"
    assert response.headers["traceparent"].startswith("00-")
    assert response.json() == {
        "detail": "Internal server error.",
        "request_reference": "failure-request",
    }
    record = json.loads(caplog.records[-1].message)
    assert record["request_id"] == "failure-request"
    assert record["error_class"] == "RuntimeError"
    assert caplog.records[-1].levelno == logging.ERROR
    assert "private evidence payload" not in caplog.text
