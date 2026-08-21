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

## API

- `POST /risk-methodologies` creates one immutable methodology version.
- `POST /risks` creates one stable risk identity.
- `GET /risks` lists the verified tenant's risk identities and latest snapshot.
- `POST /risks/{risk_id}/assessments` appends an assessment using an expected
  revision number.
- `GET /compliance-workspace` includes `risks`, risk posture counts, and risk
  next actions.

Writes require the compliance-governance purpose and the existing verified
tenant boundary. Local preview headers remain compatibility inputs only; they
are not authentication. Evidence payloads are never returned from the risk
projection.

## Deliberate ceiling

This slice does not claim treatment completion, risk acceptance, portfolio
aggregation, audit-program completion, or certification. Above-appetite rows
point to the next treatment or time-bounded acceptance workflow, which must be
implemented and reviewed before a product can report that disposition.
