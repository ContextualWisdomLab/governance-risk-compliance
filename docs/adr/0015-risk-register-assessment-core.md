# ADR 0015: Versioned risk register and immutable assessment core

## Status

Accepted for the bounded buyer slice; treatment, time-bounded acceptance, and
independent closure disposition are included. Portfolio aggregation remains a
separate follow-up contract.

## Decision

Store a stable tenant risk identity separately from immutable assessment
snapshots. Every snapshot records its methodology version, likelihood, impact,
inherent score, residual score, appetite status, rationale, assessor, review
date, and optional decision reference. The method version also stores separate
appetite and tolerance thresholds plus the control-effectiveness method used
by the calculation.

Risk reduction may reference only an implemented tenant-owned
`internal_control_definition` through its scoped `control_implementation`, a
completed `control_test_result`, and purpose-bound `evidence_usage`. External
catalog identifiers are not direct risk mitigations. Multiple references to the
same implementation are rejected and operating-effective links use the
methodology's bounded factor with a minimum-factor aggregation rule; factors
are not multiplied, preventing double counting.

The application requires an expected risk revision for assessment writes and
increments the revision only after the immutable snapshot and links are
validated. SQLite and PostgreSQL guards reject updates and deletes of
methodology, assessment, assessment-link, treatment-plan, and acceptance
history. Treatment plans are versioned per risk. Acceptance is allowed only for
the latest above-appetite assessment, requires an actor other than the
assessor, has a current future-ending period, and requires escalation above
tolerance. Closure requires a fresh within-appetite assessment, an independent
approver, and a closure evidence reference; an active acceptance blocks closure.
All writes append an audit event.

## Consequences

- Officers can distinguish inherent exposure from residual exposure and
  above-appetite follow-up without a certification claim.
- The workspace can project exact tenant risk rows and deterministic next
  actions without exposing evidence payloads.
- Treatment completion and risk aggregation across a portfolio are intentionally
  not represented.

## Verification

`tests/test_risks.py` exercises local API boundaries, methodology and register
validation, optimistic concurrency, real internal-control test results,
purpose-bound evidence usage, tenant isolation, score calculation, treatment
versioning, independent acceptance, expiry actions, independent closure, and
database immutability guards. The implementation does not copy external standard text; the current
standards references are maintained in `docs/doctoring/REFERENCES.md`.
