# ADR 0010: Define SLO and error-budget contracts before alert deployment

## Status

Proposed; requires service-owner approval and collector acceptance.

## Context

The service now emits request, database transaction, and audit-write telemetry,
but it has no approved reliability targets, error-budget policy, dashboards, or
paging route. A green local test cannot prove production availability or
recovery. Alert thresholds also need to avoid high-cardinality identity and
evidence labels.

## Decision

1. Define availability, mutation-success, audit-write, and recovery SLOs in
   `docs/runbooks/slo-policy.md` with explicit good events, targets, budgets,
   owner actions, and a 30-day reporting window.
2. Use multi-window, multi-burn-rate page and ticket thresholds as starting
   policy. The [Google SRE alerting guidance](https://sre.google/workbook/alerting-on-slos/)
   is the cited baseline; service owners must approve any target or threshold
   before deployment.
3. Require collector delivery, recording rules, dashboards, paging rehearsal,
   and recovery evidence before marking the policy accepted or describing the
   service as production-ready.
4. Keep SLO labels bounded to route templates, method, status class, database
   system, environment, and outcome. Never label telemetry with tenant, actor,
   evidence, request, token, or raw path identifiers.

## Consequences

- Operators have a concrete approval artifact and next action rather than an
  unverified production claim.
- The current telemetry names map to the availability, mutation, and audit
  portions of the policy; recovery remains a rehearsed operational event.
- Dashboards and alert rules remain platform-owned integration work.

## Verification

The policy is checked into the repository, linked from the operational runbook,
and cites the official alerting baseline. Runtime acceptance remains open until
collector, dashboard, paging, and recovery evidence is attached at an exact
current source head.
