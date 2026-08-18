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
- Product CI for lint, docstring coverage, and 100% test coverage.

### Security

- Deny proxy-forwarded and non-loopback HTTP traffic by default while the runtime lacks Keyverse-backed identity and tenant authorization.
- Document the unauthenticated remote-preview environment switch as an isolated-test-only escape hatch, not as authentication.
- Preserve exact operational evidence values while requiring purpose-specific field selection, encryption, retention, and audit for the future production boundary.

### ADR

- `docs/adr/0001-control-evidence-first-slice.md` — catalog + evidence + gap query and the local-only preview boundary as the first GRC product surface.
- `docs/adr/0002-policy-versioning-official-controls.md` — versioned policies map official controls only; OPA/Rego deferred.
