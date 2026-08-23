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
- Bounded pinned-HTTPS Keyverse OIDC metadata and public-JWK loading through the provider-loader boundary, retaining exact source-byte digests and atomic last-known-good snapshots.
- HTTP route adapter that verifies Keyverse Bearer access tokens, rejects actor-header impersonation, matches declared tenant to the `org` claim, and returns only the verified officer's policies and gaps.
- Officer home (`GET /`) and officer form posts require the same Keyverse Bearer token and hide other officers' policy titles from the home page.
- Tenant-owned persistence: `policy_document`, `evidence_record`, and `audit_event` store `tenant_identifier`, migrate existing rows to `local_preview`, and isolate reads/writes by Keyverse `org`.
- OpenAPI `/openapi.json` publishes `KeyverseBearer` (`at+jwt`) on officer policy, evidence, and home operations with `grc.policy.read`, `grc.policy.write`, and `grc.evidence.write`. Catalog and `/healthz` stay public.
- Officer home browser forms store the Keyverse access token in `sessionStorage` and send it as an `Authorization: Bearer` header. Local preview without a verifier posts `X-Actor-Id` from the officer identifier instead of requiring a token.
- Officer evidence form authenticates before validating `control_ref`, so unauthenticated callers receive 401 rather than a 400 that leaked catalog well-formedness.
- Keyverse policy-gap queries count only the verified tenant's evidence bindings, so one organization's CSAP mapping cannot hide another organization's uncovered control.
- Keyverse audit attribution: `audit_event` stores issuer, OAuth client, request correlation, and `allow` without copying the access token; migration `0003_audit_attribution` backfills legacy rows as `local_preview` / `legacy_unattributed`.
- Deployment-hardening runbook for local-preview migration, rollback, JWKS rotation, issuer outage, clock skew, and emergency read-only.
- Hardened local start: `CWL_GRC_REQUIRE_KEYVERSE` refuses header-identity boots and admits only loopback TLS (`CWL_GRC_TLS_CERTFILE` / `CWL_GRC_TLS_KEYFILE` must be readable files). `cwl-grc serve` and `python -m cwl_grc` load a reviewed offline JWKS from `CWL_GRC_KEYVERSE_JWKS_PATH`. Invalid flag values fail closed. Proxy headers cannot rewrite TLS. Hardened-start and preview errors both name `CWL_GRC_EVIDENCE_KEY` for persistent stores. This is not remote production exposure.

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
- Accept only explicitly typed, signed RS256 Keyverse access tokens with exact issuer, audience, client, role, tenant, workspace, principal-kind, time, token-ID, and action-scope validation.
- Check required action scopes before consuming an optional one-time-use Keyverse token replay guard.
- Reject ID-token/access-token confusion, unsigned or alternate-algorithm tokens, unsupported critical headers, unknown or duplicate keys, private/symmetric/encryption JWKs, stale/future tokens, and client/subject confusion.
- Bound offline Keyverse JWK input to 1 MiB and support reviewed old/new public-key overlap without enabling network discovery or remote GRC traffic.
- Map a verified token that lacks an action scope to HTTP 403 through `AccessTokenScopeError` (RFC 6750 `insufficient_scope`) instead of matching exception text for `"required scope"`.
- Reject provider refresh clocks whose `tzinfo` exists without a defined UTC offset.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
- `docs/adr/0003-keyverse-jwt-access-token-profile.md` — closed RFC 9068-style Keyverse access-token profile before route and tenant integration.
- `docs/adr/0004-keyverse-oidc-provider-loading.md` — bounded pinned-HTTPS loading of Keyverse OIDC metadata and public JWKs before route and tenant integration.
- `docs/adr/0005-keyverse-http-route-enforcement.md` — Bearer access-token route enforcement using the Keyverse principal as actor, with local preview preserved when no verifier is configured.
- `docs/adr/0006-keyverse-tenant-owned-persistence.md` — persist Keyverse `org` on policy, evidence, and audit rows and isolate reads/writes by tenant.
- `docs/adr/0007-keyverse-openapi-security.md` — publish Keyverse Bearer security schemes on officer policy and evidence OpenAPI operations.
- `docs/adr/0008-keyverse-audit-event-attribution.md` — persist Keyverse issuer, client, and request correlation on audit events without storing bearer tokens.
- `docs/adr/0009-keyverse-required-tls-admission.md` — require an injected Keyverse verifier and loopback TLS before a hardened local start.
