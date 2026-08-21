# ADR 0016: Tenant-scoped risk portfolio indicators

## Status

Accepted for the bounded compliance-workspace read model.

## Context

The risk register now preserves methodology-versioned assessment and
disposition history, but an officer still needs a portfolio view to answer how
many risks are unassessed, above appetite, overdue, actively accepted, being
treated, or closed. Adding a composite residual-risk score would compare
values produced by different methodology versions and could turn a count
projection into an unsupported certification claim.

## Decision

Add `risk_portfolio` to the tenant-scoped `/compliance-workspace` posture
projection. It reports total, assessed, unassessed, above-appetite,
within-appetite, overdue, treatment-plan, active-treatment,
active-acceptance, closure, and closed-risk counts, plus deterministic
status/category breakdowns.

The projection consumes the already tenant-filtered risk register and latest
assessment/disposition maps. An acceptance counts as active only when it
references the latest assessment and its validity interval contains the
observation time. Closed risks are excluded from overdue counts. The
projection does not sum, average, rank, or otherwise compare residual scores
across methodology versions, and it creates no database table or cross-service
copy of authoritative data.

The customer-facing UI remains the separately governed Figma/Storybook
authority in PR34; this ADR defines the backend read contract only and has no
new Figma file ID.

## Consequences

- Officers receive actionable portfolio counts while exact risk rows remain
  available for drill-down and audit traceability.
- Tenant isolation and purpose authorization reuse the existing workspace
  boundary; no new identity or ownership model is introduced.
- Portfolio scorecards and cross-methodology severity ranking remain explicit
  future work requiring a reviewed normalization standard and evidence.

## Verification

`tests/test_risks.py` covers real tenant-scoped assessment, treatment,
acceptance, closure, overdue, and unassessed records, including the empty
portfolio edge case. The full suite retains 100% statement/branch coverage and
100% docstring coverage.
