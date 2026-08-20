# CHANGELOG.md

## Unreleased

### Added

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
- Provider-neutral Keyverse JWT access-token verification kernel and typed authenticated-principal contract.
- Bounded Keyverse OIDC Discovery and JWKS loading with exact issuer, host, address, TLS identity, response-size, and key-rotation provenance controls.
- Verified-principal HTTP authorization for protected policy and evidence mutations.
- Non-null tenant ownership on policy, evidence, binding, and audit records, including a migration backfill for pre-tenant local-preview data.
- Versioned evidence encryption metadata, bounded old/new key overlap, and audited idempotent rewrap support.
- Evidence retention metadata and purpose-authorized legal-hold placement/release without altering stored payloads.
- Truthful `/readyz` and `/startupz` contracts, bounded PostgreSQL connection setup, drain rejection, W3C correlation, and redaction-safe JSON request logs.
- OpenTelemetry request traces, request rate/duration metrics, authorization-denial metrics, and route-template cardinality protection with standard OTLP export configuration.
- Database session transaction outcome/duration metrics with rollback-safe request dependency instrumentation.
- Bounded SQLAlchemy database-pool size, checked-in, checked-out, and overflow gauges labeled only by database system.
- Declared recovery-event count and duration metrics with bounded replacement/read-only modes and success/failure outcomes.
- Proposed availability, mutation-success, audit-write, and recovery SLO/error-budget policy with bounded-label burn-rate alert thresholds.
- Tenant-scoped internal-control model: immutable definition versions, scoped implementations and owners, reviewed many-to-many catalog mappings, design/operating tests, exceptions, deficiencies, evidence usage, and explicit coverage statuses.
- Additive migration that classifies preexisting direct evidence bindings as `unassessed` without inventing effectiveness.
- Tenant-scoped obligation register: source revisions, jurisdictions, applicability decisions, legal references, commitments, proposed policy/control links awaiting independent review, regulatory changes, immutable impact assessments, and overdue/upcoming worklists for Issue #28.

### Security

- Always deny proxy-forwarded and non-loopback HTTP traffic while the runtime lacks complete Keyverse-backed identity and tenant authorization; remove the unauthenticated remote-preview bypass entirely.
- Bind both standalone server entry points to `127.0.0.1`.
- Require durable Fernet key material for every persistent evidence store; limit ephemeral keys to explicitly selected in-memory tests.
- Enforce append-only `audit_event` history and finalized `policy_version` / `policy_control_mapping` immutability with SQLite and PostgreSQL database triggers.
- Serialize policy edition allocation through an optimistic database counter and return `409 Conflict` to stale writers.
- Preserve exact operational evidence values while requiring purpose-specific field selection, encryption, retention, and audit for the future production boundary.
- Pin the CSAP 2026.07 catalog provenance to the official KISA resource notice rather than a generic product page.
- Pin every Product workflow action to an immutable commit and verify the exact pull-request head before testing.
- Replace mutable `pip install` resolution with `uv sync --locked`, verify lock freshness, and reject any tracked or untracked dirty tree on every Product run.
- Accept only explicitly typed, signed RS256 Keyverse access tokens with exact issuer, audience, client, role, tenant, workspace, principal-kind, time, token-ID, and action-scope validation.
- Reject ID-token/access-token confusion, unsigned or alternate-algorithm tokens, unsupported critical headers, unknown or duplicate keys, private/symmetric/encryption JWKs, stale/future tokens, and client/subject confusion.
- Bound offline Keyverse JWK input to 1 MiB and support reviewed old/new public-key overlap without enabling remote GRC traffic.
- Require `grc.policy.read` for policy and policy-gap reads in Keyverse mode, and derive every protected mutation actor and tenant from the verified bearer rather than caller identity headers.
- Hide cross-tenant policy and evidence identifiers behind tenant-filtered reads and `404 Not Found` mutation responses.
- Pair tenant and parent identifiers with named composite foreign-key constraints for new schemas and idempotent tenant-parent guards for existing SQLite and PostgreSQL stores.
- Require explicit evidence key IDs and authenticated tenant-record encryption context; reject unknown, revoked, mismatched, or tampered encryption metadata without falling back to another key.
- Require retention metadata and a verified `grc.evidence.retention` purpose for legal-hold changes; leave destructive disposition and remote access disabled until their operating contracts exist.
- Keep `/healthz` dependency-free; require database, schema receipts, seed rows, integrity guards, key round-trip, and environment checks before startup admits traffic.
- Enable SQLite foreign-key enforcement and require PostgreSQL-compatible boolean constraints for the internal-control schema.
- Add SQLite/PostgreSQL composite tenant guards and immutable-history triggers for obligation and regulatory-change records; require the dedicated `compliance_governance` purpose on the new JSON workflow.
- Enforce null-safe obligation-target uniqueness, savepoint-backed concurrent-create conflicts, and proposed-only obligation-link insertion so creation cannot self-assert approval.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
- `docs/adr/0003-keyverse-jwt-access-token-profile.md` — closed RFC 9068-style Keyverse access-token profile before route and tenant integration.
- `docs/adr/0004-keyverse-oidc-provider-loading.md` — bounded issuer metadata and public-key loading without arbitrary discovery or ambient network authority.
- `docs/adr/0005-verified-tenant-record-isolation.md` — verified tenant ownership, protected reads, cross-tenant non-disclosure, and database-enforced tenant-parent relationships.
- `docs/adr/0006-evidence-keyring-and-rotation.md` — provider-neutral evidence key inventory, context-bound envelopes, and bounded rewrap behavior.
- `docs/adr/0007-evidence-retention-and-legal-hold.md` — retention metadata and tenant-scoped legal holds without destructive evidence mutation.
- `docs/adr/0008-operational-readiness-and-correlation.md` — liveness/readiness/startup separation, drain state, correlation, and safe structured logging.
- `docs/adr/0009-opentelemetry-request-telemetry.md` — isolated OpenTelemetry request spans/metrics, standard OTLP export, and bounded route attributes.
- `docs/adr/0010-slo-and-error-budget-contract.md` — proposed SLO, error-budget, and multi-window alert contract pending collector acceptance.
- `docs/adr/0011-separate-external-requirements-and-internal-controls.md` — separate external requirements, internal controls, scoped implementations, testing, evidence usage, and explicit effectiveness projection.
- `docs/adr/0012-obligation-applicability-and-regulatory-change.md` — source-backed obligation, applicability, commitment, and change-impact history separate from control effectiveness.
