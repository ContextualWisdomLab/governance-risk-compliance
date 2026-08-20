# CHANGELOG.md

## Unreleased

### Added

- Versioned policy authoring: `policy_document`, `policy_version`, and `policy_control_mapping` mapped only to official catalog identifiers.
- Policy-gap query that reuses `control_evidence_binding` (no second evidence model).
- Officer home form to author a policy and see uncovered policy requirements.
- `cwl-grc` officer CLI: `policy author|revise|list`, `gaps`, `bind`, and `serve`.
- Explicit database-operator CLI: `cwl-grc database migrate` owns schema/reference changes and `cwl-grc database check` verifies compatibility without DDL.
- Runtime schema profiles: local `development` preparation and fail-closed `runtime` compatibility mode.
- Hash-locked `psycopg[binary]` 3.3.4 support through the exact `postgresql+psycopg` SQLAlchemy dialect.
- Digest-pinned PostgreSQL 18.4 integration workflow covering clean install, DDL-free restart, advisory migration locking, trigger parity, session timeouts, and reference-data compatibility.
- PostgreSQL schema-lifecycle ADR, standards doctoring, expand/contract guidance, failed-migration handling, rollback boundaries, and emergency read-only runbook.
- Official policy-deployment identifiers: SOC 2 `CC5.3` and COSO 2013 Principle 12.
- First buyer slice: official CSAP / SOC 2 / ISMS-P / ISO/IEC 27001:2022 / NIST SP 800-53 Rev. 5 / COSO 2013 / COSO 2017 control seeds.
- Evidence create and control–evidence binding with declared actor/purpose audit context and encryption at rest.
- Uncovered-control query and officer home that states the next action.
- `/healthz` probe, standalone `python -m cwl_grc` entry, and `create_app()` module factory.
- Product CI for lint, docstring coverage, and 100% statement/branch test coverage.
- Hash-locked `uv.lock` dependency graph for runtime and development dependencies.
- Versioned schema-upgrade receipts for existing first-slice stores.

### Changed

- Shared `control_framework`, `control_item`, and `authorization_purpose` reference data is now bootstrapped only by a schema-owning path; runtime refuses missing or incompatible vocabulary instead of silently repairing it.
- Production application replicas no longer create tables, apply migrations, install triggers, or seed reference data during startup.
- PostgreSQL support is scoped to major version 18 and exercised on 18.4; other majors are unsupported until they receive a separate compatibility decision and exact CI lane.

### Security

- Always deny proxy-forwarded and non-loopback HTTP traffic while the runtime lacks Keyverse-backed identity and tenant authorization; remove the unauthenticated remote-preview bypass entirely.
- Bind both standalone server entry points to `127.0.0.1`.
- Require durable Fernet key material for every persistent evidence store; limit ephemeral keys to explicitly selected in-memory tests.
- Enforce append-only `audit_event` history and finalized `policy_version` / `policy_control_mapping` immutability with SQLite and PostgreSQL database triggers.
- Serialize policy edition allocation through an optimistic database counter and return `409 Conflict` to stale writers.
- Acquire a fixed PostgreSQL transaction advisory lock before schema mutation so concurrent migration owners fail before interleaving DDL or reference-data writes.
- Require remote PostgreSQL `sslmode=verify-full`; permit disabled TLS only in an explicit loopback integration-test profile.
- Bound PostgreSQL connect, statement, lock, idle-transaction, pool-acquisition, overflow, and recycle behavior; require `lock_timeout < statement_timeout`.
- Refuse uninitialized, behind, ahead, table-incomplete, or reference-incompatible schemas before runtime sessions are opened.
- Preserve exact operational evidence values while requiring purpose-specific field selection, encryption, retention, and audit for the future production boundary.
- Pin the CSAP 2026.07 catalog provenance to the official KISA resource notice rather than a generic product page.
- Pin every Product and PostgreSQL workflow action and service image to immutable identities and verify the exact pull-request head before testing.
- Replace mutable `pip install` resolution with `uv sync --locked`, verify lock freshness, and reject any tracked or untracked dirty tree on every Product run.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
- `docs/adr/0006-explicit-postgresql-schema-lifecycle.md` — separate migration ownership from runtime, close the PostgreSQL connection policy, and reject unsupported schema/reference states before traffic.
