# Control catalog and evidence binding — first slice

## Outcome

A compliance officer can list CSAP / SOC 2 / ISMS-P controls, see which still lack evidence, and bind the next artifact. The same service also seeds ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017 so later mappings stay on official identifiers.

## Approaches considered

1. **Catalog-only spreadsheet** — cheap, but cannot bind evidence or query gaps.
2. **Recommended: modular FastAPI kernel** — installable `cwl_grc` package plus `python -m cwl_grc` standalone process, SQLite-ready schema, purpose-bound evidence encryption, `/healthz`.
3. **Full GRC suite** — policy/risk/audit workflows now. Out of scope; those bodies come after this slice is buyer-real.

## Runtime

- Standalone: bind `0.0.0.0:$PORT`, probe `/healthz`.
- Module: `from cwl_grc import create_app`.
- Other CWL products consume control/evidence contracts only.

## Data (3NF, two-or-more-word snake_case)

`control_framework` → `control_item`; `authorization_purpose`; `evidence_record`; `control_evidence_binding`; `audit_event`.

## Buyer surface

Officer home lists uncovered CSAP / SOC 2 / ISMS-P rows with the next action: attach evidence. JSON APIs list controls, list uncovered controls, create evidence, and bind evidence. Catalog reads are public text. Evidence create/read/bind require actor + purpose. PII in evidence stays usable (encrypted at rest, never masked).
