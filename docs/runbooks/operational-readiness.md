# Operational readiness runbook

## First action

Call `GET /healthz`, then `GET /readyz`. If `/healthz` is not `200`, restart or
replace the process. If `/healthz` is `200` and `/readyz` is `503`, stop routing
new traffic and use the returned `checks[*].reason_code` to choose the next
action below.

## Reason-code actions

| Reason code | Meaning | Next action |
| --- | --- | --- |
| `database_unreachable` | The store could not answer the bounded probe. | Verify PostgreSQL reachability and credentials, then retry `/readyz`; do not expose a degraded instance. |
| `schema_incompatible` / `schema_migration_incomplete` | Required tables or migration receipts are absent. | Stop deployment, inspect migration receipts, and run the reviewed migration path; never delete or rebuild a customer store as a shortcut. |
| `seed_state_incomplete` | Official catalog or purpose vocabulary is incomplete. | Restore the checked-in catalog seed path and rerun startup against the same database. |
| `integrity_guards_incomplete` | Database immutability or tenant-parent guards are absent. | Keep the instance out of service and reinstall the dialect-specific guards through the reviewed startup path. |
| `evidence_key_unavailable` / `evidence_key_round_trip_failed` | The configured evidence key cannot encrypt and decrypt a private probe. | Restore the approved key configuration/provider and verify the exact key inventory; never rotate by overwriting or logging raw keys. |
| `keyverse_configuration_required` / `remote_access_boundary_disabled` | Production mode is not a supported remote deployment. | Return to `local_preview` or complete the Keyverse-backed remote boundary and its independent review before retrying. |
| `draining` | The process is shutting down. | Wait for the replacement instance to become ready; retry mutations against the ready instance. |

## Correlation and data safety

Copy only `X-Request-ID`, `traceparent`, status, route template, and reason code
into an incident. Do not copy bearer tokens, encryption keys, request bodies,
plaintext evidence, or raw tenant/actor identifiers into tickets or logs.

## OpenTelemetry request telemetry

Set the standard `OTEL_EXPORTER_OTLP_ENDPOINT` to the approved collector before
starting a reviewed deployment. The service emits `http.server.request.count`,
`http.server.request.duration`, `cwl_grc.authorization.denial.count`,
`cwl_grc.database.transaction.count`, and
`cwl_grc.database.transaction.duration` with method, registered route template,
status, database system, outcome, and environment-scoped resource attributes.
If no endpoint is configured, the local bounded reader supports tests and
developer diagnostics but is not an external monitoring path.

Next action: verify collector delivery, dashboards, SLO/error-budget policy,
burn-rate alerts, and paging before treating telemetry as production evidence.

## Current boundary

This runbook covers the implemented local readiness contract and request-level
OpenTelemetry emission. Database pool metrics, SLO/error budgets,
burn-rate alerts, restore/rollback rehearsals, and a production paging
integration must be added before describing the service as production-ready.
