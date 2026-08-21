# ADR 0013: Compose the first tenant-scoped compliance workspace read model

## Status

Proposed; requires independent review and protected merge at the exact source
head. This is a local-preview read contract, not production authorization or a
compliance certification claim.

## Context

The control catalog, obligation worklist, and policy-gap query already carry
tenant filters and conservative statuses, but an officer has no single
posture read. Adding a second persistence model would duplicate truth and
create a new consistency boundary before evidence requests, risks, audit
programs, and exports have their own contracts.

## Decision

1. Add `GET /compliance-workspace` as a read-only composition of
   `list_control_coverage`, `list_obligation_worklist`, and `list_policy_gaps`.
2. Require the existing `compliance_governance` purpose and, when Keyverse is
   enabled, the existing `grc.compliance.read` action scope.
3. Return exact row projections, deterministic next actions, and explicit
   `not_yet_projected` areas. Distinguish distinct obligations from
   applicability/review work items when reporting posture. Never derive a
   synthetic compliance score or treat evidence presence as control
   effectiveness.
4. Keep the buyer-workspace visual system in the Figma/Storybook PR34 design
   authority; this PR supplies the authenticated data contract only.

## Consequences

The first workspace becomes useful without a new table or migration, and the
same tenant isolation rules are reused. Catalog coverage is preloaded in
tenant-scoped batches so a workspace read does not issue one status query per
catalog item. The endpoint remains bounded to the three existing projections.
Evidence request state, risks, audit engagement, controlled export, data-room
access, and production deployment remain follow-up work with separate
authorization and provenance decisions.

## Verification

`tests/test_obligations.py` verifies missing and wrong scopes, two verified
tenants, exact obligation scope, policy-gap isolation, explicit posture counts,
and the declared projection ceiling. The full product suite must retain 100%
statement and branch coverage and 100% public docstring coverage.
