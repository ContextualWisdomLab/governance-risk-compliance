# CWL GRC

Author a versioned policy, see which mapped CSAP / SOC 2 TSC / ISMS-P / ISO/IEC 27001 controls still need evidence, then attach the next artifact.

This repository is the ContextualWisdomLab home for policy, control, risk, evidence, and compliance-audit truth. Other CWL services consume the control and evidence contracts only.

## Run the developer preview

1. Install and start the officer tools with `python -m pip install -e ".[dev]"` and `python -m cwl_grc`, or run `cwl-grc serve`.
2. Open `/` from the same machine, author the next policy, and map it only to official catalog identifiers.
3. Read the policy-gap list and attach the next evidence on an uncovered mapped control.
4. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}`.

The HTTP surface is an **unauthenticated developer preview**, not a production identity boundary. `X-Actor-Id` and `X-Purpose` declare audit context and purpose; they do not authenticate an actor. The app therefore rejects proxy-forwarded or non-loopback traffic by default. Do not route external traffic until Keyverse-backed OIDC, tenant authorization, and deployment hardening are implemented.

`CWL_GRC_ALLOW_UNAUTHENTICATED_REMOTE_PREVIEW=1` is an explicit unsafe escape hatch for an isolated test environment only. It is not authentication and must not be used for customer or Internet traffic.

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

Each command prints JSON that states the next action. The CLI is also a developer-preview interface until the same identity and tenant controls are available.

## What this slice does

| Action | Where |
| --- | --- |
| Author or revise a policy | `POST /policy-documents`, `POST /policy-documents/{id}/versions`, or `cwl-grc policy` |
| List policies | `GET /policy-documents` |
| See policy/control gaps | `GET /policy-gaps?policy_document_id=`, `cwl-grc gaps`, or `/` |
| List official controls | `GET /controls?framework=csap_2026` |
| See catalog coverage gaps | `GET /controls/uncovered?framework=soc2_tsc_2017` |
| Store evidence | `POST /evidence-records` with `X-Actor-Id` and `X-Purpose: evidence_binding` |
| Bind evidence | `POST /control-evidence-bindings` or `cwl-grc bind` |
| Probe | `GET /healthz` |

Policy authoring requires the declared purpose `policy_authoring`. Evidence create and bind require `evidence_binding`. Policies map only to seeded official identifiers: CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

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
python -m cwl_grc
```

```python
from cwl_grc import create_app

app = create_app()
```

Set `CWL_GRC_EVIDENCE_KEY` (Fernet) in any durable environment. Without it the process uses an ephemeral key and evidence will not survive a restart. Set `CWL_GRC_DATABASE_URL` when you are not using the local SQLite file.

## Citations

Authoritative identifiers and APA 7th references live in `docs/doctoring/REFERENCES.md`. If a citation and the code disagree, fix the code.
