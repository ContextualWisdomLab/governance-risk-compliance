# Control catalog and evidence binding — first slice

> Historical first-slice design. The current product model is specified in
> `docs/product/internal-control-model.md` and ADR 0011; direct evidence
> bindings are compatibility data and do not imply effectiveness.

## Outcome

A compliance officer can author a versioned policy mapped to official CSAP / SOC 2 / ISMS-P / ISO 27001 controls, see which mapped requirements lack an operating-effective conclusion, and preserve the next artifact for a reviewed control test. The same service also seeds NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017 so later mappings stay on official identifiers.

## Approaches considered

1. **Catalog-only spreadsheet** — cheap, but cannot bind evidence or query gaps.
2. **Recommended: modular FastAPI kernel** — installable `cwl_grc` package plus `python -m cwl_grc` standalone process, SQLite-ready schema, purpose-bound evidence encryption, `/healthz`.
3. **Full GRC suite** — residual risk scoring and audit-workflow bodies remain later. Policy authoring is in this slice (ADR 0002).

## Runtime

- Standalone: bind `0.0.0.0:$PORT`, probe `/healthz`.
- Module: `from cwl_grc import create_app`.
- Other CWL products consume control/evidence contracts only.

## Data (3NF, two-or-more-word snake_case)

`policy_document` → `policy_version` → `policy_control_mapping` → `control_item`; `control_framework`; `authorization_purpose`; `evidence_record`; legacy `control_evidence_binding`; internal-control definitions, implementations, mappings, tests, deficiencies, exceptions, and `evidence_usage`; `audit_event`.

## Buyer surface

Officer home authors a policy, lists explicit uncovered statuses, and stores evidence for a future control test. JSON and CLI list policies, list policy gaps, create evidence, and preserve compatibility bindings. Catalog reads are public text. Policy authoring requires `policy_authoring`. Evidence create/read/bind require `evidence_binding`. PII in evidence stays usable (encrypted at rest, never masked).
