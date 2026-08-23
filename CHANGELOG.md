# CHANGELOG.md

## Unreleased

### Added

- Versioned policy authoring: `policy_document`, `policy_version`, and `policy_control_mapping` mapped only to official catalog identifiers.
- Policy-gap query that reuses `control_evidence_binding` (no second evidence model).
- Officer home form to author a policy and see uncovered policy requirements.
- `cwl-grc` CLI: `policy author|revise|list`, `gaps`, `bind`, and `serve`.
- Official policy-deployment identifiers: SOC 2 `CC5.3` and COSO 2013 Principle 12.
- First officer slice: official CSAP / SOC 2 / ISMS-P / ISO/IEC 27001:2022 / NIST SP 800-53 Rev. 5 / COSO 2013 / COSO 2017 control seeds.
- Evidence create and control–evidence binding with declared actor/purpose audit context and encryption at rest.
- Uncovered-control query and officer home that states the next action.
- `/healthz` probe, standalone `python -m cwl_grc` entry, and `create_app()` module factory.
- Product CI for lint, docstring coverage, and 100% statement/branch test coverage.
- Hash-locked `uv.lock` dependency graph for runtime and development dependencies.
- Versioned schema-upgrade receipts for existing first-slice stores.
- `docs/product-technical-gap-baseline.md` with observed product truth, the live PR queue, officer-visible production and domain gaps, standards corrections, ownership boundaries, and exact next actions. The 2026-08-24 refresh records PR #58 hosted Devin success, terminal hosted check counts for merge-ready develop PRs, PR #34 Strix provider-unavailable, and central `.github` #1257 still blocked on Strix/OpenCode.
- Wave 1 legacy-binding projection identity: `binding_id` plus `control_item_id`, tenant-scoped through the bound evidence record, with `unassessed` fan-out only after an authorized `control_requirement_mapping` exists.
- `docs/product/grc-domain-completion-roadmap.md` defining the closed obligation → requirement → policy → internal control → implementation → test/evidence → risk/audit → remediation → controlled-reporting loop and its release gates.
- Current doctoring references for ISO 37301:2021 and Amendment 1:2024, ISO 19011:2026 Edition 4, OSCAL 1.2.3, and the NIST OLIR Program without claiming certification or source-text redistribution rights.

### Security

- Always deny proxy-forwarded and non-loopback HTTP traffic while the runtime lacks Keyverse-backed identity and tenant authorization; remove the unauthenticated remote-preview bypass entirely.
- Bind both standalone server entry points to `127.0.0.1`.
- Require durable Fernet key material for every persistent evidence store; limit ephemeral keys to explicitly selected in-memory tests.
- Enforce append-only `audit_event` history and finalized `policy_version` / `policy_control_mapping` immutability with SQLite and PostgreSQL database triggers.
- Serialize policy edition allocation through an optimistic database counter and return `409 Conflict` to stale writers.
- Preserve exact operational evidence values while requiring purpose-specific field selection, encryption, retention, and audit for the future production boundary.
- Pin the CSAP 2026.07 catalog provenance to the official KISA resource notice rather than a generic product page.
- Pin every Product workflow action to an immutable commit and verify the exact pull-request head before testing.
- Replace mutable `pip install` resolution with `uv sync --locked`, verify lock freshness, and reject any tracked or untracked dirty tree on every Product run.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
- `docs/adr/0011-separate-external-requirements-and-internal-controls.md` — preserve external catalogs while adding distinct internal-control definitions, implementations, reviewed mappings, tests, effectiveness results, deficiencies, and purpose-bound evidence usage before risk and audit depend on the model.