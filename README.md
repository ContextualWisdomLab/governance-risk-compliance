# CWL GRC

See which CSAP, SOC 2, and ISMS-P controls still need evidence, then attach the next artifact.

This repository is the ContextualWisdomLab home for policy, control, risk, evidence, and compliance-audit truth. Other CWL services consume the control and evidence contracts only.

## Do this next

1. Run the officer home: `python -m cwl_grc` (listens on `0.0.0.0:$PORT`, default 8080).
2. Open `/` and read the uncovered CSAP / SOC 2 / ISMS-P rows.
3. Attach the next evidence on a gap. Officer names and contact details stay usable; they are not masked.
4. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}` before you route traffic.

## What this slice does

| Action | Where |
| --- | --- |
| List official controls | `GET /controls?framework=csap_2026` |
| See coverage gaps | `GET /controls/uncovered?framework=soc2_tsc_2017` |
| Store evidence | `POST /evidence-records` with `X-Actor-Id` and `X-Purpose: evidence_binding` |
| Bind evidence | `POST /control-evidence-bindings` |
| Probe | `GET /healthz` |

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

## Product boundary

| This repo owns | Other CWL homes consume only |
| --- | --- |
| Policy, control, risk, evidence, audit truth | Orgmetra employment, Keyverse identity, AIS books, Billing metering, naruon office, EA, ontology |

CSAP, SOC 2, and ISMS-P are product controls here. SAST, Strix, CodeQL, and Semgrep stay with CWL Security.

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
