# CLAUDE.md

CWL GRC is the ContextualWisdomLab system of record for policy, control, risk, evidence, and compliance-audit truth. It is not a SAST scanner, identity provider, HRIS, ledger, or ontology portal.

## Core boundaries

- This repo owns GRC truth and the control/evidence contracts other CWL services consume.
- Keyverse owns identity. Orgmetra owns employment. AIS owns books. Billing owns metering. naruon owns office work. enterprise-architecture-core owns EA. semantic-data-portal owns ontology.
- CWL Security owns SAST/Strix/CodeQL/Semgrep.
- The current HTTP surface is a local developer preview. Purpose headers are declarations for audit context, not authentication. Remote deployment is forbidden until Keyverse-backed identity and tenant authorization exist.
- Operational PII remains exact for authorized workflows. Do not destructively mask it; omit unrelated fields from purpose-specific views and exports, and enforce encryption, retention, and audit.
- The issue #30 buyer-workspace design authority is Figma file `ta1jjWSjmADz2BFxka9UPs` plus repository Storybook. Keep shared semantic tokens and repeated state/action components aligned across both.
- Officer summaries are projections. Keep `unknown`, `not assessed`, `stale`, `blocked`, and `access denied` explicit, and expose an exact-value alternative for every aggregate visual.
- Supported officer-workspace journeys target WCAG 2.2 AA and must preserve keyboard/focus, screen-reader semantics, touch alternatives, reduced motion, responsive behavior, and print/PDF content. Customer-facing copy uses officer/organization language, not “Buyer”.

## Writing guidance

Customer-facing copy must state the next action and the actual deployment boundary. Avoid vague AI claims. If a citation and the code conflict, fix the code. Do not invent a second control catalog. Do not add OPA/Rego unless a later slice needs a PDP.