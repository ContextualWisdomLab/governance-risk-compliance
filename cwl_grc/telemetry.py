"""OpenTelemetry request instrumentation for the GRC service boundary."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from opentelemetry import propagate
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode


SERVICE_NAME = "cwl-grc"
OTEL_ENDPOINT_ENVIRONMENT_VARIABLE = "OTEL_EXPORTER_OTLP_ENDPOINT"


class RequestTelemetry:
    """Emit bounded-cardinality request traces and metrics through OpenTelemetry."""

    def __init__(self, environment: str) -> None:
        """Create isolated providers for one application instance."""
        resource = Resource.create(
            {
                "service.name": SERVICE_NAME,
                "deployment.environment.name": environment,
            }
        )
        self._metric_reader = InMemoryMetricReader()
        metric_readers: list[MetricReader] = [self._metric_reader]
        self._tracer_provider = TracerProvider(resource=resource)
        if os.environ.get(OTEL_ENDPOINT_ENVIRONMENT_VARIABLE):
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter())
            )
            metric_readers.append(
                PeriodicExportingMetricReader(OTLPMetricExporter())
            )
        self._meter_provider = MeterProvider(
            metric_readers=metric_readers,
            resource=resource,
        )
        meter = self._meter_provider.get_meter(SERVICE_NAME)
        self._tracer = self._tracer_provider.get_tracer(SERVICE_NAME)
        self._request_count: Counter = meter.create_counter(
            "http.server.request.count",
            unit="{request}",
            description="HTTP requests completed by the GRC service.",
        )
        self._request_duration: Histogram = meter.create_histogram(
            "http.server.request.duration",
            unit="s",
            description="HTTP request duration in seconds.",
        )
        self._authorization_denials: Counter = meter.create_counter(
            "cwl_grc.authorization.denial.count",
            unit="{denial}",
            description="HTTP authorization denials observed by the service.",
        )
        self._transaction_count: Counter = meter.create_counter(
            "cwl_grc.database.transaction.count",
            unit="{transaction}",
            description="Database session transaction outcomes.",
        )
        self._transaction_duration: Histogram = meter.create_histogram(
            "cwl_grc.database.transaction.duration",
            unit="s",
            description="Database session transaction duration in seconds.",
        )
        self._audit_write_count: Counter = meter.create_counter(
            "cwl_grc.audit.write.count",
            unit="{write}",
            description="Audit events committed or rejected by the database transaction.",
        )
        self._recovery_event_count: Counter = meter.create_counter(
            "cwl_grc.recovery.event.count",
            unit="{event}",
            description="Declared recovery events observed by the service.",
        )
        self._recovery_duration: Histogram = meter.create_histogram(
            "cwl_grc.recovery.duration",
            unit="s",
            description="Declared recovery event duration in seconds.",
        )
        self._database_engine = None
        self._pool_gauges = tuple(
            meter.create_observable_gauge(
                f"cwl_grc.database.pool.{name}",
                callbacks=[lambda _options, method=method: self._observe_pool_metric(method)],
                unit="{connection}",
                description=description,
            )
            for name, method, description in (
                (
                    "size",
                    "size",
                    "Configured database connection-pool size.",
                ),
                (
                    "checked_out",
                    "checkedout",
                    "Database connections currently checked out of the pool.",
                ),
                (
                    "checked_in",
                    "checkedin",
                    "Database connections currently checked in to the pool.",
                ),
                (
                    "overflow",
                    "overflow",
                    "Database connection-pool overflow count.",
                ),
            )
        )

    @property
    def metric_reader(self) -> InMemoryMetricReader:
        """Expose the bounded local reader for integration evidence and tests."""
        return self._metric_reader

    def bind_database_engine(self, engine: Any) -> None:
        """Bind one SQLAlchemy engine for low-cardinality pool observations."""
        self._database_engine = engine

    def _observe_pool_metric(self, method_name: str) -> tuple[Observation, ...]:
        """Read one supported SQLAlchemy pool value when the pool exposes it."""
        if self._database_engine is None:
            return ()
        reader = getattr(self._database_engine.pool, method_name, None)
        if not callable(reader):
            return ()
        return (
            Observation(
                reader(),
                {"db.system.name": self._database_engine.dialect.name},
            ),
        )

    @contextmanager
    def server_span(
        self,
        method: str,
        route: str,
        headers: Mapping[str, str],
    ) -> Iterator[Span]:
        """Create a W3C-parented server span without high-cardinality attributes."""
        parent_context = propagate.extract(dict(headers))
        with self._tracer.start_as_current_span(
            f"HTTP {method}",
            context=parent_context,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span.set_attribute("http.request.method", method)
            span.set_attribute("http.route", route)
            try:
                yield span
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise

    def record_request(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record request rate, duration, and authorization denials."""
        attributes: dict[str, Any] = {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status_code,
        }
        self._request_count.add(1, attributes)
        self._request_duration.record(
            duration_seconds,
            {
                "http.request.method": method,
                "http.route": route,
            },
        )
        if status_code in {401, 403}:
            self._authorization_denials.add(1, {"http.route": route})

    def record_database_transaction(
        self,
        database_system: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        """Record a bounded database transaction outcome and duration."""
        attributes = {"db.system.name": database_system, "cwl_grc.outcome": outcome}
        self._transaction_count.add(1, attributes)
        self._transaction_duration.record(duration_seconds, {"db.system.name": database_system})

    def record_audit_write(
        self,
        database_system: str,
        outcome: str,
        event_count: int,
    ) -> None:
        """Record the bounded count and outcome of one audit write batch."""
        self._audit_write_count.add(
            event_count,
            {"db.system.name": database_system, "cwl_grc.outcome": outcome},
        )

    def record_recovery_event(
        self,
        recovery_mode: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        """Record one bounded replacement or read-only recovery event."""
        if recovery_mode not in {"replacement", "read_only"}:
            raise ValueError("Recovery mode must be replacement or read_only.")
        if outcome not in {"success", "failure"}:
            raise ValueError("Recovery outcome must be success or failure.")
        attributes = {
            "cwl_grc.recovery.mode": recovery_mode,
            "cwl_grc.outcome": outcome,
        }
        self._recovery_event_count.add(1, attributes)
        self._recovery_duration.record(duration_seconds, attributes)

    def shutdown(self) -> None:
        """Flush configured exporters and release provider resources."""
        self._tracer_provider.shutdown()
        self._meter_provider.shutdown()


def span_traceparent(span: Span) -> str:
    """Return the W3C traceparent for one emitted server span."""
    context = span.get_span_context()
    return (
        f"00-{context.trace_id:032x}-{context.span_id:016x}-"
        f"{int(context.trace_flags):02x}"
    )
