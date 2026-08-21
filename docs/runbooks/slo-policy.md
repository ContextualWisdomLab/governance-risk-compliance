# CWL GRC SLO and error-budget policy

## Status

Proposed product policy. These targets are not production evidence until a
service owner approves them, the collector receives the required metrics, and
the dashboards and paging routes are rehearsed.

## Service-level objectives

The reporting window is 30 calendar days. A good event is counted only when the
service can prove the event from correlated telemetry; missing telemetry is
not silently treated as success.

| SLO | Good event | Proposed target | Error budget | Next action |
| --- | --- | ---: | ---: | --- |
| Availability | An admitted request finishes below 500 without an infrastructure failure. | 99.9% | 0.1% | Stop routing to a degraded instance and inspect `/readyz` plus request traces. |
| Mutation success | An authorized policy/evidence mutation commits with a 2xx response. | 99.9% | 0.1% | Review transaction outcome, authorization denial, and database traces before retrying. |
| Audit write | Every attempted audit event commits in the same transaction as its authorized mutation. | 99.99% | 0.01% | Freeze further mutations, preserve the request reference, and run the audit-failure runbook. |
| Recovery | A declared service-impacting failure reaches a ready replacement or documented read-only state within 15 minutes. | 95% | 5% | Start the restore/rollback rehearsal and record the recovery evidence. |

Availability and mutation SLOs must exclude intentionally rejected requests
that have a valid authorization or input reason code; infrastructure and
unexpected 5xx failures remain bad events. Audit-write failures are always bad
events, including when the parent mutation is rolled back.

## Alert policy

Use multi-window, multi-burn-rate alerts after the collector and recording rules
exist. The starting policy follows the official Google SRE recommendation of
page alerts at 2% budget consumption in one hour or 5% in six hours, and a
ticket at 10% in three days:

| Notification | Long window | Short window | Burn rate | Action |
| --- | ---: | ---: | ---: | --- |
| Page | 1 hour | 5 minutes | 14.4x | Wake the on-call; stop unsafe traffic and preserve correlated evidence. |
| Page | 6 hours | 30 minutes | 6x | Wake the on-call; begin dependency or rollback diagnosis. |
| Ticket | 3 days | 6 hours | 1x | Open a reliability work item before the budget is exhausted. |

Do not put tenant IDs, actor IDs, evidence IDs, request IDs, or raw routes in
metric labels. Dashboards may group by service environment, route template,
method, status class, database system, and bounded outcome only.

## Current implementation boundary

The service currently emits request count/duration, authorization denial,
database transaction outcome/duration, audit-write outcome, and bounded
database pool gauges through OpenTelemetry. The pool gauges are
`cwl_grc.database.pool.size`, `cwl_grc.database.pool.checked_out`,
`cwl_grc.database.pool.checked_in`, and `cwl_grc.database.pool.overflow`; each
uses only `db.system.name`. The recovery event contract emits
`cwl_grc.recovery.event.count` and `cwl_grc.recovery.duration` with only
`replacement`/`read_only` modes and `success`/`failure` outcomes after an
external coordinator declares an event. This is not recovery evidence by
itself. Collector delivery, recording rules, dashboards, paging integration,
and restore/rollback rehearsal remain the next actions. `/readyz` remains the
first operator check.
