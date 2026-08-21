# OpenTelemetry evidence references

These references ground the organization telemetry evidence boundary in
standards and official project documentation. The GRC decision remains narrow:
raw telemetry stays in the approved observability platform, while GRC stores an
aggregate acceptance result through its existing evidence contract.

## References

OpenTelemetry Authors. (2025, December 3). *Instrumentation: OpenTelemetry
Python*. OpenTelemetry. https://opentelemetry.io/docs/languages/python/instrumentation/

OpenTelemetry Authors. (n.d.). *General semantic conventions*. Retrieved
August 21, 2026, from https://opentelemetry.io/docs/specs/semconv/general/

OpenTelemetry Authors. (n.d.). *Semantic conventions*. Retrieved August 21,
2026, from https://opentelemetry.io/docs/specs/otel/semantic-conventions/

World Wide Web Consortium. (n.d.). *Trace Context* (W3C Recommendation).
https://www.w3.org/TR/trace-context/

## Applied boundary

- Python services use the OpenTelemetry API and SDK at the application
  boundary, with OTLP export enabled only through the approved deployment
  endpoint.
- Route, service, error, and dependency attributes follow bounded semantic
  conventions; prompts, answers, post bodies, images, secrets, and unbounded
  identifiers remain excluded.
- W3C `traceparent` propagation correlates one authorized operation across
  `cwl-grc`, `lineageweave`, `contextual-orchestrator`, and Valkey access spans.
