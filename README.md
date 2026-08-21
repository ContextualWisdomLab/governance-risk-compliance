# CWL GRC

Author a versioned policy, see each mapped CSAP / SOC 2 TSC / ISMS-P / ISO/IEC 27001 control status, then establish the next reviewed control test.

This repository is the ContextualWisdomLab home for policy, control, risk, evidence, and compliance-audit truth. Other CWL services consume the control and evidence contracts only.

## Run the developer preview

1. Install with `python -m pip install -e ".[dev]"`.
2. Generate and store a Fernet key as `CWL_GRC_EVIDENCE_KEY` before using any persistent database.
3. Run `python -m cwl_grc` or `cwl-grc serve`; both start Uvicorn on loopback only.
4. Open `/` from the same machine, author the next policy, and map it only to official catalog identifiers.
5. Read the policy-gap list, distinguish `unknown`, `unassessed`, design, operating, stale, exception, and ineffective statuses, then establish the next control test.
6. Register an authoritative obligation source and exact revision, record an evidenced applicability decision, and review overdue/upcoming obligations from `/obligations`.
7. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}`.
8. Confirm `/readyz` returns `200` with database, schema, seed, guard, key, identity, and lifecycle checks; use `/startupz` to inspect the checks that admitted the process.
9. Set the standard `OTEL_EXPORTER_OTLP_ENDPOINT` only when an approved collector is available; request traces and low-cardinality request metrics are then exported asynchronously.

The HTTP surface is an **unauthenticated developer preview**, not a production identity boundary. Local HTTP mutations use the fixed `local_development_actor` audit actor; caller-supplied `X-Actor-Id` is ignored. `X-Purpose` declares purpose but does not authenticate an actor. The command-line server binds to `127.0.0.1`, and the app always rejects proxy-forwarded or non-loopback traffic. No runtime bypass exists. Do not route external traffic until Keyverse-backed OIDC, tenant authorization, and deployment hardening are implemented.

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
| See explicit catalog coverage statuses | `GET /controls?framework=soc2_tsc_2017` or `GET /controls/uncovered?framework=soc2_tsc_2017`; Keyverse mode requires `grc.control.read` and `X-Purpose: coverage_review` |
| Store evidence | `POST /evidence-records` with `X-Purpose: evidence_binding`; local HTTP uses the fixed `local_development_actor` |
| Store compatibility evidence binding | `POST /control-evidence-bindings` or `cwl-grc bind`; direct bindings remain `unassessed` until a scoped control test uses the evidence |
| Register source and exact revision | `POST /obligations/sources`, `POST /obligations/sources/{id}/revisions` with `X-Purpose: compliance_governance` |
| Register and decide an obligation | `POST /obligations`, `POST /obligations/{id}/applicability-decisions`; decisions require rationale, evidence reference, period, and next review |
| Propose obligation truth | `POST /obligations/{id}/requirements` to a finalized policy or internal control; the response remains `proposed` until independent review |
| Review obligations and source changes | `GET /obligations` (`upcoming_days` 0–3660), `POST /obligations/changes`, and `POST /obligations/changes/{id}/impact-assessments` |
| Liveness probe | `GET /healthz` (dependency-free) |
| Readiness probe | `GET /readyz` (returns `503` with stable reason codes when traffic is unsafe) |
| Startup probe | `GET /startupz` (reports the checks completed before admission) |
| OpenTelemetry telemetry | Standard OTLP endpoint from `OTEL_EXPORTER_OTLP_ENDPOINT`; request, session-transaction, database-pool, and declared-recovery metrics use bounded attributes; no endpoint means bounded local collection for tests/developer diagnostics |

Policy authoring requires the declared purpose `policy_authoring`. Evidence create and bind require `evidence_binding`. Obligation source, decision, mapping, and change workflows require `compliance_governance`. Policies map only to seeded official identifiers: CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

## Integrity guarantees

- `audit_event` rows are append-only at the database boundary.
- A `policy_version` is created open, receives its mappings, and is finalized exactly once.
- Finalized policy text and mappings cannot be updated, deleted, or extended through SQL.
- `policy_document.current_version_number` serializes revision allocation; a stale writer receives `409 Conflict` and must reload.
- Versioned schema upgrades leave `schema_migration` receipts and upgrade existing first-slice stores before integrity triggers are installed.
- Internal controls are separate from official catalog requirements: published definition versions, scoped implementations, reviewed mappings, design/operating tests, deficiencies, exceptions, and purpose-approved evidence usage project explicit coverage statuses.
- Database guards reject mismatched control-definition/implementation test graphs, and coverage ignores retired definitions and inactive test plans.
- Obligations are separate from framework controls: exact source revisions, jurisdiction/scope, evidenced applicability decisions, commitments, proposed policy/control links, immutable change intake, and impact/re-approval worklists preserve legal and operational truth without copying source text. Requirement creation never self-asserts approval.
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

The default `CWL_GRC_ENVIRONMENT=local_preview` is the only environment admitted by this loopback-only slice. A production value fails startup until the Keyverse remote boundary is implemented. Requests receive `X-Request-ID` and W3C `traceparent` headers; structured logs and OpenTelemetry attributes use route templates and never include bearer tokens, keys, plaintext evidence, raw tenant/actor identifiers, or request bodies. The next action for production telemetry is to configure and verify the organization collector, dashboards, SLOs, and paging policy.

## Citations

Authoritative identifiers and APA 7th references live in `docs/doctoring/REFERENCES.md`. If a citation and the code disagree, fix the code.
