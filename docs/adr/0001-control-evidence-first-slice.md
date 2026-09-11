# ADR 0001: Control catalog and evidence binding as the first GRC slice

## Status

Accepted for the first buyer-facing product slice.

## Context

A compliance officer could not see which CSAP / SOC 2 / ISMS-P controls had evidence, nor attach the next artifact. The repository had only a customer README.

The first runtime also lacked an identity provider and tenant-authorization adapter. A caller-supplied actor or purpose header can record intent, but it cannot prove who the caller is. Exposing that surface remotely would make operational evidence and usable PII reachable through an unauthenticated interface.

Policy and audit truth also require stronger guarantees than an ORM convention. Concurrent writers must not allocate the same edition, finalized policy text and mappings must not change, append-only audit events must resist ordinary SQL mutation, and persistent ciphertext must remain decryptable after restart.

## Decision

Ship a modular FastAPI kernel that:

1. Seeds official identifiers from CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.
2. Stores evidence with a declared audit purpose and encrypts payloads at rest without destructively masking operational values.
3. Binds evidence to one official control and queries uncovered controls.
4. Exposes `/healthz` and runs standalone or as `create_app()`.
5. Treats the HTTP surface as a local developer preview. It always rejects proxy-forwarded and non-loopback traffic until Keyverse-backed identity and tenant authorization are implemented.
6. Requires durable evidence-key material for every persistent database; only explicitly selected in-memory tests may use an ephemeral key.
7. Creates each policy edition as unfinalized, writes its official-control mappings, and then permits exactly one transition to finalized.
8. Protects `audit_event`, finalized `policy_version`, and `policy_control_mapping` with database triggers for SQLite and PostgreSQL.
9. Uses `policy_document.current_version_number` as an optimistic concurrency token; stale revisions fail with `409 Conflict` instead of guessing another edition number.
10. Applies versioned schema upgrades before integrity triggers and records each completed upgrade in `schema_migration`.

Rejected alternatives:

- A catalog-only spreadsheet cannot bind evidence.
- Caller-supplied purpose headers alone are not an authentication system.
- An environment switch that exposes the unauthenticated HTTP surface would bypass the intended trust boundary.
- A random key for a persistent database makes evidence undecryptable after restart.
- ORM-only immutability can be bypassed by another session or direct SQL.
- Retrying a uniqueness failure without a durable concurrency token can duplicate side effects or hide stale intent.
- Destructive masking would impair evidence work; production views instead need authenticated, purpose-specific field selection that omits unrelated fields.

Policy authoring was later confirmed as part of this same slice; see ADR 0002.

## Consequences

Other CWL products can eventually consume the control/evidence HTTP contracts through an authenticated boundary. Until that boundary exists, operators use the loopback preview or the local CLI and must not route customer or Internet traffic to the service.

Existing first-slice stores are upgraded in place before integrity triggers are installed. A stale policy writer must reload. Operators must provision and retain Fernet key material before opening a persistent store. Database portability is intentionally limited to dialects with reviewed integrity DDL; unknown dialects fail closed.

Residual risk scoring, Keyverse OIDC and tenant authorization, production deployment hardening, and audit-workflow bodies remain later slices. Product CI is local to this repo; organization Security, OpenCode, and Noema lanes remain centrally owned.

## References

American Institute of Certified Public Accountants. (2022). *2017 trust services criteria for security, availability, processing integrity, confidentiality, and privacy (with revised points of focus—2022)* (TSP Section 100). https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

Committee of Sponsoring Organizations of the Treadway Commission. (2013). *Internal control—Integrated framework*. https://www.coso.org/guidance-on-ic

Committee of Sponsoring Organizations of the Treadway Commission. (2017). *Enterprise risk management—Integrating with strategy and performance*. https://www.coso.org/_files/ugd/3059fc_61ea5985b03c4293960642fdce408eaa.pdf

International Organization for Standardization. (2022). *Information security, cybersecurity and privacy protection—Information security management systems—Requirements* (ISO/IEC 27001:2022). https://www.iso.org/standard/27001

Korea Internet & Security Agency. (2023, November 23). *정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서* [Information security and personal information management system (ISMS-P) certification criteria guide]. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlRcsrmDetail.do?searchRcsrmMngId=RCSRMID_000000010105

Korea Internet & Security Agency. (2026, July 6). *2026년 클라우드서비스 보안인증기준 해설서(2026.07)* [2026 cloud service security certification criteria commentary]. File corrected July 28, 2026. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlVrtlRcsrmList.do?rcsrmMenuCd=1003&searchKeyword=%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C%EC%84%9C%EB%B9%84%EC%8A%A4+%EB%B3%B4%EC%95%88%EC%9D%B8%EC%A6%9D%EA%B8%B0%EC%A4%80+%ED%95%B4%EC%84%A4%EC%84%9C

Ross, R., & Pillitteri, V. (2020). *Security and privacy controls for information systems and organizations* (NIST Special Publication 800-53 Rev. 5). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-53r5
