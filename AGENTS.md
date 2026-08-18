# AGENTS.md

## Mission

Build ContextualWisdomLab GRC as the system of record for policy, control, risk, evidence, and compliance-audit truth. The first buyer slice is versioned policy authoring + official control catalog + evidence binding + uncovered policy/control query.

## Hard rules

- Never bypass branch protection, required checks, or independent review. Never self-APPROVE, never `--admin`, never mark Draft as Ready.
- Never use `COPILOT_GITHUB_TOKEN` as a model credential. LLM tests, if any, use `NVIDIA_NIM_API_KEY` only. Prefer contextual-orchestrator when a model is required.
- Never copy Orgmetra, Keyverse, AIS, Billing, naruon, EA, or semantic-data-portal product bodies. Those services consume control/evidence contracts only.
- Never take `.github` OpenCode, Noema, or Security lanes, TEPP, or LineageWeave #74.
- CSAP / SOC 2 / ISMS-P are product controls in this repo. Do not invent a second SAST stack.
- Never blanket-mask PII. Keep it usable with purpose-limited authorization, encryption at rest, and audit.
- Never dummy-commit or force-push.
- Work only in this cloud environment. Do not clone onto a laptop.

## Database rules

- Owned objects use two-or-more-word `snake_case` names.
- 3NF is the default.
- Catalog identifiers must be official CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, or COSO 2017 identifiers.

## Documentation rules

Keep README, AGENTS, CLAUDE, ARCHITECTURE, CHANGELOG, ADRs, and doctoring references current with code. Customer-facing copy states the next action: author a policy, review policy gaps, attach evidence, or probe `/healthz`.

## Quality rules

- Production code requires public docstrings.
- Focused statement and branch coverage is 100% where tooling exposes it.
- Tests use real catalog identifiers, not toys.
- Product CI lives in `.github/workflows/product.yml` only.
