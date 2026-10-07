# ADR 0017: Audit program, engagement, finding, and closure records

- Status: Proposed
- Date: 2026-10-06
- Decision owners: CWL GRC maintainers
- Related issues: #4, #12, #13, #14, #27

Numbered 0017 because other open branches already use ADR numbers 0003 through
0016.

## Context

Issue #14 asks for an audit-management slice. An audit authority plans an audit
program; an independent, competent team runs an engagement against stated
criteria; auditors document reproducible sampling and evidence references;
findings are issued with revision history; remediation owners record actions;
an independent auditor retests; and a finding closes only after a passing
retest or a time-bounded risk-acceptance decision by a different authority.
Overdue remediation must be visible.

The repository cannot meet that outcome with existing objects:

- `audit_event` is the append-only application action log. It records that an
  actor declared a purpose and changed a row. It is not an audit program,
  engagement, procedure, finding, or closure, and reusing it for those would
  mix the system's own audit trail with the subject matter of an audit.
- Issue #27, the internal-control model in ADR 0011, is not merged. There is no
  `internal_control_definition`, `control_implementation`, or `evidence_usage`
  table yet. Audit criteria can therefore reference only official
  `control_item` rows, and the internal control actually tested cannot yet be
  recorded as a foreign key.
- Issue #13, governed risk assessment and risk acceptance, is not merged. There
  is no risk register, risk-acceptance workflow, or acceptance authority model
  to which a finding could be handed.
- Issue #4, Keyverse-backed identity and tenant authorization, is not merged.
  `X-Actor-Id` and `X-Purpose` remain caller declarations, not authentication.
  Role separation enforced against those declarations is a workflow rule, not
  proof that two different people acted.

ISO 19011:2026 and the IIA Global Internal Audit Standards (effective
January 9, 2025) describe audit-programme management, auditor competence and
independence, sampling, findings, and follow-up. This slice uses those concepts
as design input only.

## Decision

Add a service module `cwl_grc/audit_management.py`, models in
`cwl_grc/models.py`, and JSON routes in `cwl_grc/audit_routes.py` (registered from `cwl_grc/app.py`) for the following
3NF tables. All names are two-or-more-word `snake_case`.

| Table | Role |
| --- | --- |
| `audit_program` | Period, risk-based rationale, audit authority, creator, approval (`draft` → `approved`) |
| `audit_engagement` | Engagement under an approved program; scope, period, lead auditor, status `planned` → `fieldwork` → `reporting` → `closed` |
| `engagement_criterion` | Unique engagement + official `control_item_id`; nullable opaque `internal_control_reference` placeholder for Issue #27 |
| `engagement_team_member` | Unique engagement + auditor; `team_role` `lead`, `auditor`, or `supervisor`; non-empty `competence_statement` |
| `independence_declaration` | Auditor's conflict declaration for one engagement; immutable |
| `audit_procedure` | Procedure for one criterion; population description and size, selection method, sample size, optional seed |
| `audit_sample_item` | One selected 1-based population ordinal; optional population reference and exception note |
| `audit_evidence_link` | Existing `evidence_record_id` linked to exactly one procedure or sample item (CHECK constraint) |
| `audit_finding` | Finding status, remediation owner, target date, optimistic `current_revision_number` |
| `audit_finding_revision` | Append-only condition, cause, effect, severity, rating rationale, recommendation; immutable |
| `remediation_action` | Owner, due date, status; completion requires an existing evidence record |
| `finding_retest` | Independent retest result, effectiveness conclusion, required evidence record; immutable |
| `finding_closure` | One closure per finding: `retest_passed` or `risk_accepted`; immutable |

### Criteria

External requirements are audit criteria. `engagement_criterion` references an
official, seeded `control_item` (for example `isms_p_2023:2.5.1` or
`soc2_tsc_2017:CC6.1`). The nullable `internal_control_reference` string is
opaque. It is not validated and is not a foreign key; it reserves the place for
the Issue #27 internal-control implementation under test.

### Immutable history at the database boundary

`independence_declaration`, `audit_finding_revision`, `finding_retest`, and
`finding_closure` reject `UPDATE` and `DELETE` through SQLite and PostgreSQL
triggers installed by `integrity_guard_statements`, in addition to the existing
`audit_event` and policy guards. The upgrade records the idempotent
`schema_migration` receipt `0002_audit_management`.

Finding revisions only append. `audit_finding.current_revision_number` is the
optimistic concurrency token, using the same conditional-update pattern as
`policy_document.current_version_number`: a writer that sends a stale
`expected_revision` receives `409 Conflict` and must reload.

Evidence plaintext is never copied into audit tables. Procedures, sample items,
remediation completions, and retests reference `evidence_record_id`; an unknown
evidence record returns `404`.

### Reproducible sampling

`sample_size` must not exceed `population_size`, and `population_size` must be
positive.

- `seeded_random`: the service selects
  `random.Random(seed).sample(range(1, population_size + 1), sample_size)` and
  stores the ordinals sorted. Anyone holding the seed, population size, and
  sample size can reproduce the selection.
- `full_population`: `sample_size` must equal `population_size`.
- `judgmental`: the auditor supplies unique ordinals within
  `1..population_size`, and their count must equal `sample_size`.

### Role separation and state rules

- Program approval requires the approver to be the program's
  `audit_authority_actor` and not its `created_by_actor`.
- Engagements are created only under an approved program, with a period inside
  the program period.
- An engagement starts fieldwork only when it has at least one criterion,
  exactly one `lead` team member equal to `lead_auditor_actor`, at least one
  `supervisor`, a non-empty competence statement for every member, and a
  `has_conflict = false` independence declaration from every member. Otherwise
  the service returns `409` with a next action that names what is missing.
- Procedures, sample items, evidence links, and findings are accepted only
  during `fieldwork`.
- The remediation owner must not be an engagement team member.
- Only the action owner, under purpose `remediation_tracking`, completes a
  remediation action, and completion requires an existing evidence record.
- A retest requires every remediation action to be completed. The retest
  actor must be a non-conflicted team member and must not be the remediation
  owner or an action owner. A failed retest sets `retest_failed`; the finding
  stays unresolved and new actions are allowed.
- Closure with `retest_passed` requires that the latest retest passed and that
  the closing actor is the engagement lead or a supervisor, not the
  remediation owner. The finding becomes `closed`.
- Closure with `risk_accepted` requires an acceptance authority who is not the
  remediation owner and not the team member who performed the retest, and an
  expiry date after today and no more than 365 days ahead. The finding becomes
  `risk_accepted`, not `closed`. This is a bounded placeholder decision record
  until Issue #13 delivers governed risk acceptance.
- Closed and risk-accepted findings reject new revisions, actions, and
  retests.
- An engagement moves to `reporting` when all procedures are documented, and
  to `closed` only when no finding is `open`, `remediation`, or
  `retest_failed`.
- The overdue query returns open remediation actions whose `due_date` is
  before `as_of`, and unresolved findings past `target_date`.
- Every mutation appends an `audit_event` row. Unknown identifiers return `404`
  without revealing other objects. Service functions accept an injected
  `today` or `now` so tests are deterministic.

### Purposes

Add `PurposeCode.AUDIT_ENGAGEMENT` (`audit_engagement`) for planning, fieldwork,
findings, retest, and closure, and `PurposeCode.REMEDIATION_TRACKING`
(`remediation_tracking`) for remediation-owner actions.

### Rejected alternatives

- Reusing `audit_event` as the engagement or finding store mixes the system's
  action log with audit subject matter and breaks its append-only meaning.
- Mutable finding rows lose the record of what was reported and when.
- Unseeded or unrecorded sampling cannot be reperformed by a reviewer.
- Closing a finding when remediation is marked complete, without an
  independent retest, treats owner assertion as verification.
- Recording risk acceptance as `closed` would hide residual exposure.
- Copying evidence plaintext into audit tables would create a second evidence
  store; ADR 0011 keeps `evidence_record` authoritative.

## Consequences

### Positive

- An officer can trace a finding from program approval through engagement
  team, criteria, procedures, samples, evidence references, revisions,
  remediation, retest, and closure.
- Sample selections are reproducible from stored inputs.
- Finding history, independence declarations, retests, and closures resist
  ordinary SQL mutation.
- Risk-accepted findings stay distinct from closed findings and carry an
  expiry.
- Overdue remediation is queryable.

### Costs and limits

- Role separation is checked against declared actor strings. Until Keyverse
  authentication exists, one person can declare several actor identifiers.
- Criteria point at external requirements, not at the internal control that
  was tested. Coverage or effectiveness must not be inferred from a closed
  finding.
- `audit_evidence_link` will need migration when `evidence_usage` lands.
- The `risk_accepted` record is not connected to a risk register and does not
  re-open automatically on expiry.
- Additional tables, triggers, and a schema receipt increase migration surface.

## Non-claims

- This slice does not claim conformance with ISO 19011:2026 or the IIA Global
  Internal Audit Standards, and it is not a certification, attestation, or
  quality-assessment result under either.
- It provides no tenant isolation. All rows share one local store.
- `X-Actor-Id` and `X-Purpose` are declarations, not authentication.
- It is a local developer preview. The HTTP surface remains loopback-only and
  must not receive customer or Internet traffic.

## Follow-ups

- #4: replace declared actors with Keyverse-authenticated identity and tenant
  authorization, then enforce role separation against authenticated subjects.
- #12: move the audit routes onto the versioned API with idempotency,
  pagination, strict error contracts, and abuse controls before any consumer
  depends on them.
- #13: replace the `risk_accepted` placeholder with governed risk acceptance,
  owner and authority models, and expiry-driven review.
- #27: link criteria to internal-control implementations through a real
  reference, and let `evidence_usage` absorb `audit_evidence_link`.
- Not yet implemented: auditor competence evidence (beyond a statement),
  quality assessment and improvement, workpaper preparation and reviewer
  sign-off, management response, audit universe, and audit reports.

## References

The Institute of Internal Auditors. (2024). *Global Internal Audit Standards*.
https://www.theiia.org/en/standards/2024-standards/global-internal-audit-standards/

International Organization for Standardization. (2026). *Guidelines for
auditing management systems* (ISO 19011:2026, 4th ed.).
https://www.iso.org/standard/19011

Python Software Foundation. (n.d.). *random — Generate pseudo-random numbers* (Python 3.12
documentation). https://docs.python.org/3.12/library/random.html
