# ADR 0001: Control catalog and evidence binding as the first GRC slice

## Status

Accepted for the first buyer-facing product slice.

## Context

A compliance officer could not see which CSAP / SOC 2 / ISMS-P controls had evidence, nor attach the next artifact. The repository had only a customer README.

The first runtime also lacked an identity provider and tenant-authorization adapter. A caller-supplied actor or purpose header can record intent, but it cannot prove who the caller is. Exposing that surface remotely would make operational evidence and usable PII reachable through an unauthenticated interface.

## Decision

Ship a modular FastAPI kernel that:

1. Seeds official identifiers from CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.
2. Stores evidence with a declared audit purpose and encrypts payloads at rest without destructively masking operational values.
3. Binds evidence to one official control and queries uncovered controls.
4. Exposes `/healthz` and runs standalone or as `create_app()`.
5. Treats the HTTP surface as a local developer preview. It rejects proxy-forwarded and non-loopback traffic by default until Keyverse-backed identity and tenant authorization are implemented.
6. Keeps an explicitly named unauthenticated remote-preview override only for isolated testing. The override is not production authentication.

Rejected alternatives:

- A catalog-only spreadsheet cannot bind evidence.
- Caller-supplied purpose headers alone are not an authentication system.
- Destructive masking would impair evidence work; production views instead need authenticated, purpose-specific field selection that omits unrelated fields.

Policy authoring was later confirmed as part of this same slice; see ADR 0002.

## Consequences

Other CWL products can eventually consume the control/evidence HTTP contracts through an authenticated boundary. Until that boundary exists, operators use the local preview or the local CLI and must not route customer or Internet traffic to the service.

Residual risk scoring, Keyverse OIDC and tenant authorization, production deployment hardening, and audit-workflow bodies remain later slices. Product CI is local to this repo; organization Security, OpenCode, and Noema lanes remain centrally owned.
