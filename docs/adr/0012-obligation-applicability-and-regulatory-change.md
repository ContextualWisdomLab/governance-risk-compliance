# ADR 0012: Govern obligations and applicability separately from controls

## Status

Proposed; requires independent review and protected merge at the exact source
head. The implementation remains a local-preview kernel contract and does not
provide legal advice, production authorization, or self-certification.

## Context

An official framework control is not a legal applicability decision. A buyer
needs to preserve the authoritative source, exact edition, jurisdiction and
scope, decision rationale, supporting reference, review date, and later source
changes without rewriting an earlier conclusion. Contractual and voluntary
commitments also need the same policy/control workflow while remaining distinct
from legislation and regulation.

ISO 37301:2021 and its 2024 climate-action amendment are the compliance-
management research baseline. The repository stores governed references and
decisions; it does not copy protected legal or standards text.

## Decision

1. Store `regulatory_source` as a tenant-scoped pointer with source kind,
   authority, official reference, license classification, and optional lawful
   artifact reference.
2. Store immutable `source_revision` rows with publication/effective/withdrawal
   dates, content digest, edition summary, and artifact reference.
3. Store immutable `compliance_obligation` rows linked to one exact source
   revision, optional jurisdiction reference, precise scope, and valid period.
4. Store jurisdiction references, applicability rules, immutable applicability
   decisions, attributed legal interpretations, and temporal owner assignments.
   Every decision carries rationale, evidence reference, effective period, and
   next review; `not_applicable` is never represented by deletion.
5. Store `compliance_commitment` separately for contracts and voluntary
   commitments, then use `obligation_requirement` to link an approved policy or
   reviewed internal control/implementation.
6. Store immutable `regulatory_change` intake and versioned
   `change_impact_assessment` rows with owner, due date, implementation plan,
   and re-approval state. New source revisions do not mutate prior decisions.
7. Expose the vertical slice through local-only JSON officer routes. When
   Keyverse is configured, the verified principal, tenant, purpose, and scope
   are required; `X-Actor-Id` remains a declaration only in local preview.
8. Keep dashboards, exports, risk scoring, audit engagements, and a new Figma/
   Storybook component system out of this kernel slice until their owning
   contracts and buyer workspace are ready.

## Consequences

- Applicability, policy mapping, control effectiveness, and evidence sufficiency
  remain distinct facts that can be reconstructed by source edition and time.
- Cross-tenant source, obligation, decision, and impact references fail at the
  database boundary through composite foreign keys.
- The current preview can demonstrate an officer workflow but cannot be called a
  production compliance or legal conclusion until identity, authorization,
  release, and operational gates are independently evidenced.

## Verification

- `tests/test_obligations.py` covers source, revision, jurisdiction, obligation,
  applicability, commitment, owner, policy/control link, change, impact,
  worklist, protected route, rejection, tenant, and immutable-history paths.
- The local suite reports 100% production statement and branch coverage and
  100% public docstring coverage.
- A PostgreSQL 18 probe creates the schema, runs source/obligation/applicability/
  change/impact data, rejects a cross-tenant obligation, and rejects immutable
  source-revision mutation.
