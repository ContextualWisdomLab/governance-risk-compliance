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
- `docs/product-technical-gap-baseline.md` with observed product truth, the live PR queue, officer-visible production and domain gaps, standards corrections, ownership boundaries, and exact next actions. The 2026-08-24 refresh records PR #58 hosted Devin success, terminal hosted check counts for merge-ready develop PRs, PR #34 Strix provider-unavailable, Wave 0 Keyverse order `#38 → #55 → #56 → #57 → #58`, and central `.github` #1257 still behind `main` with OpenCode `CHANGES_REQUESTED`.
- Wave 1 legacy-binding projection identity: `binding_id` plus `control_item_id`, tenant-scoped through the bound evidence record, with `unassessed` fan-out only after an authorized `control_requirement_mapping` exists.
- `docs/product/grc-domain-completion-roadmap.md` defining the closed obligation → requirement → policy → internal control → implementation → test/evidence → risk/audit → remediation → controlled-reporting loop and its release gates.
- Current doctoring references for ISO 37301:2021 and Amendment 1:2024, ISO 19011:2026 Edition 4, OSCAL 1.2.3, and the NIST OLIR Program without claiming certification or source-text redistribution rights.
- Issue #14 audit-management slice (local developer preview): `audit_program`, `audit_engagement`, `engagement_criterion`, `engagement_team_member`, `independence_declaration`, `audit_procedure`, `audit_sample_item`, `audit_evidence_link`, `audit_finding`, `audit_finding_revision`, `remediation_action`, `finding_retest`, and `finding_closure`, with JSON routes under `/audit-programs`, `/audit-engagements`, `/audit-procedures`, `/audit-findings`, `/remediation-actions`, and `/audit-remediation/overdue` that each return `next_action`. The declared purpose is validated before the request body, so a missing purpose returns `401` or `403` even when the body is also invalid.
- Audit criteria reference official `control_item` rows; `internal_control_reference` is a nullable opaque placeholder until the Issue #27 internal-control model lands.
- Reproducible `seeded_random` sampling via `random.Random(seed).sample`, stored as sorted 1-based ordinals, plus validated `judgmental` and `full_population` selections.
- Remediation tracking with evidence-backed completion, independent retest, closure only after a passing retest, and a `risk_accepted` placeholder decision record with an expiry of at most 365 days pending Issue #13.
- Overdue-remediation query for open actions past their due date and unresolved findings past their target date.
- Declared purposes `audit_engagement` and `remediation_tracking`.
- Doctoring reference for the IIA Global Internal Audit Standards (2024, effective January 9, 2025), without a conformance claim.

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
- Reject update/delete of `independence_declaration`, `audit_finding_revision`, `finding_retest`, and `finding_closure` with SQLite and PostgreSQL triggers, recorded by the `0002_audit_management` schema receipt.
- Serialize finding revisions through `audit_finding.current_revision_number`; stale `expected_revision` writers receive `409 Conflict`.
- Enforce audit role separation on declared actors: program approver is the audit authority and not the creator; remediation owners are not engagement team members; retesters are non-conflicted team members who are not remediation or action owners; risk-acceptance authority differs from the remediation owner and the retester. These checks are not authentication until Keyverse identity exists.
- Keep audit tables free of evidence plaintext by referencing `evidence_record_id` only; unknown evidence and audit identifiers return `404`.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
- `docs/adr/0011-separate-external-requirements-and-internal-controls.md` — preserve external catalogs while adding distinct internal-control definitions, implementations, reviewed mappings, tests, effectiveness results, deficiencies, and purpose-bound evidence usage before risk and audit depend on the model.
- `docs/adr/0017-audit-program-engagement-finding-closure.md` (Proposed) — Issue #14 audit program, engagement, sampling, finding revision, remediation, retest, and closure records; explicit non-claims for ISO 19011:2026 and IIA Global Internal Audit Standards conformance, tenant isolation, and authentication; follow-ups #4, #12, #13, and #27.
