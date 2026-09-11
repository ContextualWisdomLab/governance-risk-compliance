# CLAUDE.md

CWL GRC is the ContextualWisdomLab system of record for policy, control, risk, evidence, and compliance-audit truth. It is not a SAST scanner, identity provider, HRIS, ledger, or ontology portal.

## Core boundaries

- This repo owns GRC truth and the control/evidence contracts other CWL services consume.
- Keyverse owns identity. Orgmetra owns employment. AIS owns books. Billing owns metering. naruon owns office work. enterprise-architecture-core owns EA. semantic-data-portal owns ontology.
- CWL Security owns SAST/Strix/CodeQL/Semgrep.
- The current HTTP surface is a local developer preview. Purpose headers are declarations for audit context, not authentication. When Keyverse is configured, audit events store issuer, client, and request correlation without copying the access token. Remote deployment is forbidden until Keyverse-backed identity and tenant authorization exist.
- Operational PII remains exact for authorized workflows. Do not destructively mask it; omit unrelated fields from purpose-specific views and exports, and enforce encryption, retention, and audit.

## Writing guidance

Customer-facing copy must state the next action and the actual deployment boundary. Avoid vague AI claims. If a citation and the code conflict, fix the code. Do not invent a second control catalog. Do not add OPA/Rego unless a later slice needs a PDP.
