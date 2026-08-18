# CLAUDE.md

CWL GRC is the ContextualWisdomLab system of record for policy, control, risk, evidence, and compliance-audit. It is not a SAST scanner, identity provider, HRIS, ledger, or ontology portal.

## Core boundaries

- This repo owns GRC truth and the control/evidence contracts other CWL services consume.
- Keyverse owns identity. Orgmetra owns employment. AIS owns books. Billing owns metering. naruon owns office work. enterprise-architecture-core owns EA. semantic-data-portal owns ontology.
- CWL Security owns SAST/Strix/CodeQL/Semgrep.

## Writing guidance

Customer-facing copy must state the next action: list uncovered controls, attach evidence, review a binding, or probe `/healthz`. Avoid vague AI claims. If a citation and the code conflict, fix the code.
