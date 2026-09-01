# CWL GRC

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ContextualWisdomLab/governance-risk-compliance)

**Turn policy, control, risk, and evidence work into an auditable compliance workflow instead of a spreadsheet handoff.**

Author a versioned policy, see which mapped CSAP / SOC 2 TSC / ISMS-P / ISO/IEC 27001 controls still need evidence, then attach the next artifact. This repository is the ContextualWisdomLab authority for policy, control, risk, evidence, and compliance-audit truth; other products consume those contracts rather than maintaining competing copies.

The current HTTP application is a **loopback-only developer preview**, not a production compliance service or certification claim. It is useful for evaluating the domain workflow and contracts while identity, tenant authorization, deployment hardening, and production evidence remain explicit gaps.

## What you can do now

| Job | Current capability |
| --- | --- |
| Maintain policy history | Author and revise versioned policy documents with finalized immutable versions |
| Map obligations | Bind policies to seeded official control identifiers |
| Find evidence gaps | See mapped controls that still lack evidence |
| Retain operational evidence | Store encrypted evidence records and bind them to controls |
| Reconstruct change | Use append-only audit events and schema-migration receipts |
| Integrate locally | Use the CLI, loopback HTTP API, or `create_app()` module boundary |

Policy authoring requires the declared purpose `policy_authoring`. Evidence create and bind require `evidence_binding`. Policies map only to seeded official identifiers for CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.

Framework keys: `csap_2026`, `soc2_tsc_2017`, `isms_p_2023`, `iso27001_2022`, `nist_sp_800_53_r5`, `coso_ic_2013`, `coso_erm_2017`.

## Run the developer preview

1. Install with `python -m pip install -e ".[dev]"`.
2. Generate and store a Fernet key as `CWL_GRC_EVIDENCE_KEY` before using any persistent database.
3. Run `python -m cwl_grc` or `cwl-grc serve`; both start Uvicorn on loopback only.
4. Open `/` from the same machine, author the next policy, and map it only to official catalog identifiers.
5. Read the policy-gap list and attach the next evidence on an uncovered mapped control.
6. Confirm `/healthz` returns `{"status":"ok","service":"cwl-grc"}`.

The HTTP surface is an **unauthenticated developer preview**, not a production identity boundary. `X-Actor-Id` and `X-Purpose` declare audit context and purpose; they do not authenticate an actor. The command-line server binds to `127.0.0.1`, and the app rejects proxy-forwarded or non-loopback traffic. Do not route external traffic until Keyverse-backed OIDC, tenant authorization, and deployment hardening are implemented.

## Operator CLI

```bash
cwl-grc policy author --title "Logical Access Policy" --body "Least privilege." \
  --map csap_2026:10.2.1 --map soc2_tsc_2017:CC6.1 --actor officer-park
cwl-grc gaps --policy-id <policy_document_id>
cwl-grc bind --framework csap_2026 --identifier 10.2.1 \
  --title "CSAP 10.2.1 register" --payload "reviewed approval evidence" \
  --actor officer-park
cwl-grc policy list
```

The data commands `policy author`, `policy revise`, `policy list`, `gaps`, and `bind` print JSON that states the next action. `cwl-grc serve` starts the local Uvicorn server and does not print data JSON. Running `cwl-grc policy` without `author`, `revise`, or `list` is invalid and exits with code 2. The CLI remains a developer-preview interface until the same identity and tenant controls are available.

## HTTP surface

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

| This repository owns | Outside this repository |
| --- | --- |
| Policy, control, risk, evidence, and audit truth | Employment records, identity, accounting books, billing metering, enterprise architecture, ontology, and other systems of record |

CSAP, SOC 2, and ISMS-P are product-control catalogs here. SAST, Strix, CodeQL, and Semgrep remain security engineering evidence, not compliance-control truth. Open Policy Agent / Rego is not a policy-document store and is not used as one in this slice.

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

## Current maturity

Package metadata is `0.1.0`, but source metadata and passing tests are not certification, production deployment, customer adoption, or release evidence. The current slice is intended for local evaluation and contract integration. Production use still requires authenticated identity, tenant authorization, deployment and key-management hardening, operational evidence, and the repository's documented release/governance gates.

## Documentation

- [Public documentation home](docs/index.md)
- [Architecture](ARCHITECTURE.md)
- [Security policy and trust boundaries](SECURITY.md)
- [Product/technical gap baseline](docs/product-technical-gap-baseline.md)
- [Authoritative catalog references and APA 7th citations](docs/doctoring/REFERENCES.md)
- [Change history](CHANGELOG.md)

If a citation and the code disagree, fix the code or the cited contract rather than presenting unsupported compliance truth.

## License

ContextualWisdomLab original source and documentation in this repository are licensed under the [Apache License 2.0](LICENSE). Third-party Python packages, standards publications, control catalogs, external services, and other independently licensed material retain their own terms; the repository license does not relicense them. Commercially incompatible inbound software or assets are not accepted as normal product dependencies.
