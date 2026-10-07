# CWL GRC

Author a versioned policy, see which mapped CSAP / SOC 2 TSC / ISMS-P / ISO/IEC 27001 controls still need evidence, then attach the next artifact.

This repository is the ContextualWisdomLab home for policy, control, risk, evidence, and compliance-audit truth. Other CWL services consume the control and evidence contracts only.

## Run the developer preview

1. Install with `python -m pip install -e ".[dev]"`.
2. Generate and store a Fernet key as `CWL_GRC_EVIDENCE_KEY` before using any persistent database.
3. Run `python -m cwl_grc` or `cwl-grc serve`; both start Uvicorn on loopback only.
4. Open `/` from the same machine, author the next policy, and map it only to official catalog identifiers.
5. Read the policy-gap list and attach the next evidence on an uncovered mapped control.
6. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}`.

The HTTP surface is an **unauthenticated developer preview**, not a production identity boundary. `X-Actor-Id` and `X-Purpose` declare audit context and purpose; they do not authenticate an actor. The command-line server binds to `127.0.0.1`, and the app always rejects proxy-forwarded or non-loopback traffic. No runtime bypass exists. Do not route external traffic until Keyverse-backed OIDC, tenant authorization, and deployment hardening are implemented.

## Operator CLI

```bash
cwl-grc policy author --title "Logical Access Policy" --body "Least privilege." \
  --map csap_2026:10.2.1 --map soc2_tsc_2017:CC6.1 --actor officer-park
cwl-grc gaps --policy-id <policy_document_id>
cwl-grc bind --framework csap_2026 --identifier 10.2.1 \
  --title "CSAP 10.2.1 register" --payload "park@example.co.kr approved the grant." \
  --actor officer-park
cwl-grc policy list
```

The data commands `policy author`, `policy revise`, `policy list`, `gaps`, and `bind` print JSON that states the next action. `cwl-grc serve` starts the local Uvicorn server and does not print data JSON. Running `cwl-grc policy` without `author`, `revise`, or `list` is invalid and exits with code 2. The CLI remains a developer-preview interface until the same identity and tenant controls are available.

## What this slice does

| Action | Where |
| --- | --- |
| Author or revise a policy | `POST /policy-documents`, `POST /policy-documents/{id}/versions`, `cwl-grc policy author`, or `cwl-grc policy revise` |
| List policies | `GET /policy-documents` or `cwl-grc policy list` |
| See policy/control gaps | `GET /policy-gaps?policy_document_id=`, `cwl-grc gaps`, or `/` |
| List official controls | `GET /controls?framework=csap_2026` |
| See catalog coverage gaps | `GET /controls/uncovered?framework=soc2_tsc_2017` |
| Store evidence | `POST /evidence-records` with `X-Actor-Id` and `X-Purpose: evidence_binding` |
| Bind evidence | `POST /control-evidence-bindings` or `cwl-grc bind` |
| Probe | `GET /healthz` |

Policy authoring requires the declared purpose `policy_authoring`. Evidence create and bind require `evidence_binding`. Policies map only to seeded official identifiers: CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

## Audit engagements (Issue #14 slice)

Plan an audit program, run an independent engagement against official control criteria, record reproducible samples and evidence references, issue findings, track remediation, and close a finding only after an independent retest passes. This is a **local developer preview**: it runs behind the same loopback-only boundary as the rest of the app and is not a production audit system. See `docs/adr/0017-audit-program-engagement-finding-closure.md`.

Officer workflow and the next action at each step:

1. **Plan the program.** The creator records the period, risk-based rationale, and audit authority. Next: the audit authority, who must not be the creator, approves the program.
2. **Open an engagement** inside the approved program period. Next: add criteria by framework and official catalog identifier, for example `isms_p_2023` + `2.5.1` for an access-review engagement.
3. **Staff the team.** Add exactly one `lead` (the engagement's lead auditor), at least one `supervisor`, and any `auditor` members, each with a competence statement. Next: every member files an independence declaration.
4. **Start fieldwork.** Start succeeds only when every member has declared no conflict. Otherwise the response is `409` and names what is still missing.
5. **Document procedures.** Choose `seeded_random`, `judgmental`, or `full_population` selection; the response returns the selected 1-based sample ordinals. Next: link existing evidence records to the procedure or a sample item.
6. **Issue findings** with condition, cause, effect, severity, rating rationale, and recommendation, and assign a remediation owner who is not on the engagement team. Revisions append; send the current `expected_revision` or receive `409` and reload.
7. **Remediate.** Add remediation actions with an owner and due date. Each action owner completes their own action with an existing evidence record under purpose `remediation_tracking`. Next: request an independent retest.
8. **Retest.** A non-conflicted team member who is not the remediation owner or an action owner retests with evidence. A failed retest sets `retest_failed`; add new actions and retest again.
9. **Close.** After a passing retest, the engagement lead or a supervisor closes the finding. Alternatively, a different acceptance authority records `risk_accepted` with an expiry no more than 365 days ahead. That is a placeholder decision record until Issue #13 governed risk acceptance lands; the finding is not reported as `closed`.
10. **Report and close the engagement.** Move the engagement to `reporting` once all procedures are documented, and close it once no finding is `open`, `remediation`, or `retest_failed`. Check `GET /audit-remediation/overdue` for actions and findings past their dates.

| Action | Route |
| --- | --- |
| Create a program | `POST /audit-programs` |
| Approve a program | `POST /audit-programs/{id}/approval` |
| Create an engagement | `POST /audit-programs/{id}/engagements` |
| Read an engagement | `GET /audit-engagements/{id}` |
| Add a criterion | `POST /audit-engagements/{id}/criteria` (framework + catalog_identifier) |
| Add a team member | `POST /audit-engagements/{id}/team-members` |
| Declare independence | `POST /audit-engagements/{id}/independence-declarations` |
| Start fieldwork | `POST /audit-engagements/{id}/start` |
| Move to reporting | `POST /audit-engagements/{id}/reporting` |
| Close the engagement | `POST /audit-engagements/{id}/closure` |
| Document a procedure and sample | `POST /audit-engagements/{id}/procedures` |
| Link evidence to a procedure or sample item | `POST /audit-procedures/{id}/evidence-links` |
| Issue a finding | `POST /audit-engagements/{id}/findings` |
| Revise a finding | `POST /audit-findings/{id}/revisions` |
| Read a finding with full revision history | `GET /audit-findings/{id}` |
| Add a remediation action | `POST /audit-findings/{id}/remediation-actions` |
| Complete a remediation action | `POST /remediation-actions/{id}/completion` |
| Record a retest | `POST /audit-findings/{id}/retests` |
| Close or risk-accept a finding | `POST /audit-findings/{id}/closure` |
| List overdue remediation | `GET /audit-remediation/overdue?as_of=YYYY-MM-DD` |

Every request sends `X-Actor-Id` and `X-Purpose`, and the declared purpose is checked before the request body. A request without the declared purpose receives `401` or `403` even when its body is also invalid. Use `audit_engagement` for planning, fieldwork, findings, retests, and closure, and `remediation_tracking` for remediation-owner actions. Every response includes `next_action`. Role separation is checked against declared actor identifiers only; it is not proof that different people acted until Keyverse identity is in place.

Limits of this slice: criteria reference official `control_item` rows; the internal control under test is an optional opaque `internal_control_reference` until Issue #27 lands. Workpaper sign-off, auditor competence evidence, quality assessment, and audit reports are not implemented. The slice does not claim conformance with ISO 19011:2026 or the IIA Global Internal Audit Standards, and it does not certify anything.

## Integrity guarantees

- `audit_event` rows are append-only at the database boundary.
- A `policy_version` is created open, receives its mappings, and is finalized exactly once.
- Finalized policy text and mappings cannot be updated, deleted, or extended through SQL.
- `policy_document.current_version_number` serializes revision allocation; a stale writer receives `409 Conflict` and must reload.
- Independence declarations, audit finding revisions, finding retests, and finding closures cannot be updated or deleted through SQL. `audit_finding.current_revision_number` serializes finding revisions the same way as policy editions.
- Audit tables reference `evidence_record_id`; they never copy evidence plaintext.
- Versioned schema upgrades leave `schema_migration` receipts and upgrade existing first-slice stores before integrity triggers are installed.
- A persistent database cannot start without explicit `CWL_GRC_EVIDENCE_KEY` material. Ephemeral keys are limited to explicitly selected in-memory tests.

## Personal-data handling

Evidence may need exact officer names, contact details, or other PII to remain operationally useful. This product does not destructively mask stored evidence. Instead, the production boundary must enforce authenticated identity, tenant and purpose authorization, encrypted storage and transport, immutable audit, retention, and purpose-specific field selection. Views and exports should omit unrelated fields rather than alter values that an authorized workflow needs. The current local preview does not yet satisfy that production boundary.

## Product boundary

| This repo owns | Other CWL homes consume only |
| --- | --- |
| Policy, control, risk, evidence, audit truth | Orgmetra employment, Keyverse identity, AIS books, Billing metering, naruon office, EA, ontology |

CSAP, SOC 2, and ISMS-P are product-control catalogs here. SAST, Strix, CodeQL, and Semgrep stay with CWL Security. Open Policy Agent / Rego is not a policy-document store and is not used in this slice.

## Run standalone or as a module

```bash
python -m pip install -e ".[dev]"
export CWL_GRC_EVIDENCE_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
python -m cwl_grc
```

```python
from cwl_grc import create_app

app = create_app()
```

Set `CWL_GRC_EVIDENCE_KEY` for every durable store; startup fails when a persistent database has no key. Ephemeral key generation is limited to explicitly selected in-memory SQLite tests. Set `CWL_GRC_DATABASE_URL` when you are not using the local SQLite file.

## Citations

Authoritative identifiers and APA 7th references live in `docs/doctoring/REFERENCES.md`. If a citation and the code disagree, fix the code.
