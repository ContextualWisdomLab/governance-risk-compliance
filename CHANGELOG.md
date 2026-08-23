# CHANGELOG.md

## Unreleased

### Added

- Storybook CSF `play` functions for the officer workspace covering Accessibility, Touch & Interaction, Performance, Style Selection, Layout & Responsive, Typography & Color, Animation, Forms & Feedback, Navigation, and Charts & Data, with officer/organization language instead of customer-facing “Buyer” copy.
- Bounded GRC buyer-workspace design slice for issue #30 with a truthful compliance-officer posture projection, explicit `unknown`, `not assessed`, `stale`, `blocked`, and `access denied` states, persistent next actions, and an exact-value table that preserves source version, limitation, and next action.
- Figma design authority `ta1jjWSjmADz2BFxka9UPs` with desktop/mobile frames, reusable semantic components, and interaction-state contracts paired with repository Storybook.
- Storybook 10.5.10 Web Components + Vite inventory with accessibility addon coverage for desktop, mobile, stale-evidence, and access-denied states, plus an exact-PR-head build workflow.
- ADR 0012, buyer-workspace PRD/TRD, and regression tests for design authority, WCAG-oriented keyboard/focus/touch/reduced-motion/responsive/print behavior, and projection/source-of-truth boundaries.
- Checked-in npm lockfile, Node 24.18.0 pin, and exact-head Chromium interaction checks for keyboard, mobile overflow, print, and truthful preview action edges.
- Repaired the existing Figma buyer-workspace authority frames after rendered desktop/mobile inspection: the desktop header and panels fill their intended layout, and mobile alert, trace rows, and actions fit the content column without horizontal clipping.
- Added a dependency-free English/Korean message catalog, locale selector, stable `data-state` identifiers, and browser-tested Storybook/page i18n coverage for the buyer preview.
- Added the missing exact-value, provenance, limitation, and next-action row for the `Open deficiencies` posture metric.
- Aligned Storybook with the real workspace markup, added the access-denied request action, clarified the local developer-preview boundary in both locales, repaired CSS lint findings, and added release-specific NIST SP 800-53 Release 5.2.0 sources.
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

- `docs/adr/0012-grc-buyer-workspace-design-authority.md` — Figma and Storybook paired authority, semantic tokens, WCAG 2.2 AA target, exact-value alternatives, i18n contract, and projection ownership boundary.
- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query, durable history, and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
