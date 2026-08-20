# ADR 0009: Emit bounded OpenTelemetry request telemetry

## Status

Accepted for the request-level observability slice.

## Context

The readiness slice correlated safe JSON logs and W3C `traceparent` headers but
did not emit standard traces or metrics for the organization observability
platform. Raw request paths can contain evidence or tenant identifiers, so
telemetry must use registered route templates and low-cardinality attributes.

## Decision

1. Use the OpenTelemetry Python API and SDK for one isolated application
   provider. The official [OpenTelemetry Python instrumentation guidance](https://opentelemetry.io/docs/languages/python/instrumentation/)
   requires the SDK for application instrumentation.
2. Create a W3C-parented server span for each request and record request rate,
   duration, and authorization-denial metrics.
3. Use only method, registered route template, response status, and service
   environment as request telemetry attributes. Do not attach tenant, actor,
   evidence, token, request-body, or arbitrary exception identifiers.
4. Export through the standard `OTEL_EXPORTER_OTLP_ENDPOINT` configuration when
   an approved collector is configured. Keep a bounded in-process metric reader
   for local tests and developer diagnostics when no collector is configured.
5. Keep database/pool/transaction instrumentation, SLO targets, error budgets,
   dashboards, alert thresholds, paging, and collector acceptance evidence as
   explicit follow-up work. This ADR does not authorize production exposure.

## Consequences

- Operators can send request-level traces and low-cardinality metrics to the
  organization collector without introducing a second monitoring product.
- Local tests can inspect actual SDK metric data while no endpoint is configured.
- Collector delivery and dashboard/SLO policy remain deployment acceptance
  work, not a green local-preview claim.

## Verification

Tests assert request count/duration and authorization-denial metric attributes,
W3C-parented span execution, route-template redaction, exporter configuration,
and exception recording. A live PostgreSQL probe also verified readiness and
request metrics against PostgreSQL 18.6.
