# Risk register and assessment core

The risk register is the buyer-facing record of tenant-owned scenarios that
need review. A risk identity stores its scenario, category, source reference,
affected scope, owner reference, status, revision, and next review date.

An officer creates a versioned methodology before assessing risk. The current
methodology stores likelihood and impact maxima, a control-effectiveness
factor, separate appetite and tolerance thresholds, the named
control-effectiveness method, explicit aggregation rule, and rounding policy.
Each assessment is immutable and records inherent and residual scores,
appetite status, rationale, assessor, methodology identity, review date, and
optional decision reference.

Mitigation links are deliberately narrow: an implemented internal control
implementation, its completed test result, and its purpose-bound evidence
usage must all belong to the same tenant and execution chain. Catalog controls
are not direct risk bindings. A repeated implementation is rejected so the
same mitigation cannot be counted twice; effective operating links use the
methodology factor and the minimum factor across distinct implementations.

An above-appetite assessment can receive an immutable, versioned treatment plan
with a named owner, strategy, description, and due date. A risk acceptance must
reference the latest assessment, be created by an actor other than the assessor,
remain time-bounded, and include an escalation reference when residual exposure
exceeds tolerance. Both disposition records are tenant-scoped, audit-recorded,
and protected from update or deletion at the database boundary.

Closure is a separate immutable approval. It can reference only the latest
within-appetite reassessment, requires an actor other than the assessor, and
requires a closure evidence reference. An active acceptance must expire before
closure; all earlier assessments and disposition records remain available.

## API

- `POST /risk-methodologies` creates one immutable methodology version.
- `POST /risks` creates one stable risk identity.
- `GET /risks` lists the verified tenant's risk identities and latest snapshot.
- `POST /risks/{risk_id}/assessments` appends an assessment using an expected
  revision number.
- `POST /risks/{risk_id}/treatments` appends the next proposed treatment-plan
  version using an expected revision number.
- `POST /risks/{risk_id}/acceptances` records an independent, current,
  future-ending acceptance for the latest above-appetite assessment.
- `POST /risks/{risk_id}/closures` records an independent closure approval
  for the latest within-appetite reassessment after active acceptance expires.
- `GET /compliance-workspace` includes `risks`, risk posture counts, and risk
  treatment/acceptance/closure projections, and deterministic next actions.

Writes require the compliance-governance purpose and the existing verified
tenant boundary. Local preview headers remain compatibility inputs only; they
are not authentication. Evidence payloads are never returned from the risk
projection.

## Deliberate ceiling

This slice does not claim treatment completion, portfolio aggregation,
audit-program completion, or certification. A proposed
treatment still requires officer follow-through and evidence; an active
acceptance produces an expiry review action and never becomes a compliance
conclusion.
