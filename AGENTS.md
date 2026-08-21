# AGENTS.md

## Mission

Build ContextualWisdomLab GRC as the system of record for policy, control, risk, evidence, and compliance-audit truth. The first buyer slice is versioned policy authoring + official control catalog + evidence binding + uncovered policy/control query.

## Hard rules

- Never bypass branch protection, required checks, or independent review. Never self-APPROVE, never `--admin`, never mark Draft as Ready without exact-head evidence.
- Never use `COPILOT_GITHUB_TOKEN` as a model credential. LLM tests, if any, use contextual-orchestrator and the established provider-secret contract.
- Never copy Orgmetra, Keyverse, AIS, Billing, naruon, EA, or semantic-data-portal product bodies. Those services consume control/evidence contracts only.
- Never take another dedicated-writer repository's work into this branch.
- CSAP / SOC 2 / ISMS-P are product-control catalogs in this repo. Do not invent a second SAST stack or unverified control identifier.
- Never treat `X-Actor-Id` or `X-Purpose` as authentication. The HTTP surface remains local-only until Keyverse-backed identity and tenant authorization are implemented.
- Never blanket-mask or destructively alter PII needed by an authorized workflow. Protect exact values with authenticated purpose and tenant authorization, encrypted storage and transport, audit, retention, and purpose-specific field selection that omits unrelated fields.
- GRC owns the organization OpenTelemetry evidence boundary: govern collector acceptance and aggregate verification evidence here, but never copy raw spans, prompts, post bodies, provider responses, secrets, or unbounded identifiers into GRC records.
- Never dummy-commit or force-push.
- Work only in the authorized cloud environment.

## Database rules

- Owned objects use two-or-more-word `snake_case` names.
- 3NF is the default.
- Catalog identifiers must be official CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, or COSO 2017 identifiers.

## Documentation rules

Keep README, AGENTS, CLAUDE, ARCHITECTURE, CHANGELOG, ADRs, and doctoring references current with code. Customer-facing copy states the next action and accurately distinguishes a local developer preview from a production deployment.

## Quality rules

- Production code requires public docstrings.
- Production statement and branch coverage must remain 100% where tooling exposes it.
- Tests use real catalog identifiers and realistic officer workflows.
- Product CI lives in `.github/workflows/product.yml`; organization-wide review and security lanes remain centrally owned.
