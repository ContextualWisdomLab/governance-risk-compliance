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

## Officer-workspace design preview

Issue #30 has a bounded design/runtime fixture at `apps/grc-workspace/`. Its purpose is to make the commercial GRC journey reviewable before authenticated backend integration: the officer sees explicit `unknown`, `not assessed`, `stale`, `blocked`, and `access denied` states; traces a requirement through control → test → evidence; gets a concrete next action; and can reveal an exact-value table instead of relying on a badge or percentage alone.

The paired design authority is:

- Figma file `ta1jjWSjmADz2BFxka9UPs` — desktop `1:72`, mobile `1:150`, reusable tokens/components `1:2`, interaction contracts `1:227`;
- Storybook 10.5.10 — officer-workspace CSF stories with `play` functions for Accessibility, Touch & Interaction, Performance, Style Selection, Layout & Responsive, Typography & Color, Animation, Forms & Feedback, Navigation, and Charts & Data, plus `@storybook/addon-a11y`;
- ADR 0012 plus `docs/product/grc-buyer-workspace-prd.md` and `docs/product/grc-buyer-workspace-trd.md` for ownership, WCAG 2.2 AA, i18n, exact-value, and source-of-truth constraints.

For local design review, run `corepack npm ci` and `npm run storybook`; CI runs `npm run build-storybook` plus the Chromium interaction check on the exact pull-request head. This fixture and its Storybook/browser checks are **design evidence, not release/deployment evidence**. It does not authenticate a tenant, read protected APIs, create evidence requests, authorize exports, grant an auditor data room, or certify compliance/accessibility.

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

## Integrity guarantees

- `audit_event` rows are append-only at the database boundary.
- A `policy_version` is created open, receives its mappings, and is finalized exactly once.
- Finalized policy text and mappings cannot be updated, deleted, or extended through SQL.
- `policy_document.current_version_number` serializes revision allocation; a stale writer receives `409 Conflict` and must reload.
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
