# CHANGELOG.md

## Unreleased

### Added

- Machine-verifiable production-readiness manifest for identity, data, recovery, release, operations, API, risk, and audit-product gates.
- Deterministic readiness validator with ordinary structural validation and fail-closed `--require-ready` release mode.
- Pinned, least-privilege Production Readiness workflow that checks the exact source revision.
- Versioned policy authoring: `policy_document`, `policy_version`, and `policy_control_mapping` mapped only to official catalog identifiers.
- Policy-gap query that reuses `control_evidence_binding` (no second evidence model).
- Officer home form to author a policy and see uncovered policy requirements.
- `cwl-grc` CLI: `policy author|revise|list`, `gaps`, `bind`, and `serve`.
- Official policy-deployment identifiers: SOC 2 `CC5.3` and COSO 2013 Principle 12.
- First buyer slice: official CSAP / SOC 2 / ISMS-P / ISO/IEC 27001:2022 / NIST SP 800-53 Rev. 5 / COSO 2013 / COSO 2017 control seeds.
- Evidence create and control–evidence binding with declared actor/purpose audit context and encryption at rest.
- Uncovered-control query and officer home that states the next action.
- `/healthz` probe, standalone `python -m cwl_grc` entry, and `create_app()` module factory.
- Product CI for lint, docstring coverage, and 100% statement/branch test coverage.
- Hash-locked `uv.lock` dependency graph for runtime and development dependencies.
- Versioned schema-upgrade receipts for existing first-slice stores.

### Security

- Reject malformed or internally inconsistent readiness evidence and prevent release certification while any required gate remains blocked.
- Keep structural readiness validation distinct from production certification so green CI cannot erase known blockers.
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
