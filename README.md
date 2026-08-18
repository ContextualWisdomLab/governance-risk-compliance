# CWL GRC

Author a versioned policy, see which mapped CSAP / SOC 2 / ISMS-P / ISO 27001 controls still need evidence, then attach the next artifact.

This repository is the ContextualWisdomLab home for policy, control, risk, evidence, and compliance-audit truth. Other CWL services consume the control and evidence contracts only.

## Do this next

1. Run the officer tools: `python -m cwl_grc` (listens on `0.0.0.0:$PORT`, default 8080) or `cwl-grc serve`.
2. Open `/` and author the next policy. Map it only to official catalog identifiers.
3. Read the policy-gap list. Attach the next evidence on an uncovered mapped control. Officer names and contact details stay usable; they are not masked.
4. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}` before you route traffic.

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

Each command prints JSON that states the next action.

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

Policy authoring requires `X-Purpose: policy_authoring`. Evidence bind still requires `evidence_binding`. Policies map only to official identifiers: CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

## Product boundary

| This repo owns | Other CWL homes consume only |
| --- | --- |
| Policy, control, risk, evidence, audit truth | Orgmetra employment, Keyverse identity, AIS books, Billing metering, naruon office, EA, ontology |

CSAP, SOC 2, and ISMS-P are product controls here. SAST, Strix, CodeQL, and Semgrep stay with CWL Security. Open Policy Agent / Rego is not a policy-document store and is not used in this slice.

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
