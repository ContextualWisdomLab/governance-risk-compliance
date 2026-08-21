# ADR 0013: Compose the first tenant-scoped compliance workspace read model

## Status

Proposed; requires independent review and protected merge at the exact source
head. This is a local-preview read contract, not production authorization or a
compliance certification claim.

## Context

The control catalog, obligation worklist, policy-gap query, and evidence
request workflow carry tenant filters and conservative statuses, but an
officer needs one posture read. Adding duplicate posture tables would create a
new consistency boundary.

## Decision

1. Add `GET /compliance-workspace` as a read-only composition of
   `list_control_coverage`, `list_obligation_worklist`, `list_policy_gaps`,
   and `list_evidence_requests`.
2. Require the existing `compliance_governance` purpose and, when Keyverse is
   enabled, the existing `grc.compliance.read` action scope.
3. Return exact row projections, deterministic next actions, evidence-request
   state counts, and explicit `not_yet_projected` areas. Distinguish distinct
   obligations from applicability/review work items when reporting posture.
   Never derive a synthetic compliance score or treat evidence presence as
   control effectiveness.
4. Keep the buyer-workspace visual system in the Figma/Storybook PR34 design
   authority; this PR supplies the authenticated data contract only.

## Consequences

The first workspace composes five bounded projections and reuses the existing
tenant isolation and append-only audit rules. Catalog coverage is preloaded in
tenant-scoped batches so a workspace read does not issue one status query per
catalog item. Risks, audit engagement, controlled export, data-room access,
and production deployment remain follow-up work with separate authorization
and provenance decisions.

## Verification

`tests/test_obligations.py` verifies missing and wrong scopes, two verified
tenants, exact obligation scope, policy-gap isolation, explicit posture counts,
and the evidence-request projection ceiling. The risk projection adds
versioned methodology, immutable inherent/residual assessment state, versioned
treatment plans, and bounded time-limited acceptances; audit programs, exports,
and data-room access remain outside this read model.
`tests/test_evidence_requests.py`
verifies the request, submission, independent review, rejection, audit, and
tenant-parent contracts. The full product suite must retain 100% statement and
branch coverage and 100% public docstring coverage.
