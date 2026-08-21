# ADR 0012: Govern organization-wide OpenTelemetry evidence at GRC

## Status

Accepted.

## Context

The GRC service already emits bounded request, database, audit, pool, and
recovery telemetry through the standard OTLP boundary. LineageWeave,
contextual-orchestrator, and the Valkey access boundary also need correlated
traces so an operator can follow one product operation across services.

GRC is the organization home for policy, control, risk, evidence, and audit
truth. It must not become a second trace store: copying raw spans, prompts,
post bodies, provider responses, secrets, or unbounded identifiers into the
GRC database would increase both retention and disclosure risk.

## Decision

1. GRC owns the organization observability control and its verification
   evidence; the approved collector and trace backend own raw telemetry.
2. CWL services export W3C Trace Context and OTLP telemetry using registered
   service names and bounded attributes. The required first-party boundary is
   `cwl-grc`, `lineageweave`, `contextual-orchestrator`, and the Valkey access
   instrumentation used by those services.
3. A shared product session may correlate spans across services, but a GRC
   evidence record stores only a verification summary: service, contract
   version, observation window, collector result, metric/route contract, and
   redaction result. It does not store raw spans or payloads.
4. Evidence is submitted through the existing purpose-bound evidence contract
   and remains encrypted, tenant-scoped, retained, and audited. No new
   telemetry-specific table or `user_account + post_id` key is introduced.
5. A service is not described as observably production-ready until collector
   delivery, W3C propagation, bounded-cardinality checks, and rollback to the
   local no-export mode have each been verified and attached as reviewable GRC
   evidence.
6. The standard `OTEL_EXPORTER_OTLP_ENDPOINT` is the only deployment endpoint
   contract. Service-specific model, provider, prompt, and secret settings are
   outside this ADR.

## Consequences

- Operators can use GRC to prove that cross-service observability controls were
  checked without placing customer content or raw traces in the GRC store.
- LineageWeave and contextual-orchestrator can share a session correlation
  value while each service remains independently deployable.
- Valkey operations are visible as a bounded database dependency in the
  calling service; a server-native Valkey exporter is a deployment concern and
  is not fabricated by this application contract.
- Collector, dashboard, SLO, alert, and paging configuration remains platform
  work, but its acceptance result has one auditable home in GRC.

## Verification

Use [`docs/runbooks/organization-otel-evidence.md`](../runbooks/organization-otel-evidence.md)
to verify the four first-party boundaries, then submit the aggregate result
through the existing evidence workflow. Follow
[`ADR 0009`](0009-opentelemetry-request-telemetry.md) for the GRC service's
local telemetry implementation and [`ADR 0010`](0010-slo-and-error-budget-contract.md)
for the proposed GRC SLO policy.
