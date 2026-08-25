# ADR 0002: Versioned policies map only official controls

## Status

Accepted for the first buyer-facing GRC slice.

## Context

ISO/IEC 27001:2022 clause 5.2 requires a documented information security policy. Annex A control A.5.1 requires topic-specific policies to be defined, approved, published, and reviewed. COSO Internal Control (2013) Principle 12, and AICPA SOC 2 CC5.3 which restates it, require the organization to deploy control activities through policies and the procedures that put those policies into action. KISA ISMS-P 1.1.5 and Korea CSAP 1.1.1 state the same obligation for Korean certifications.

A compliance officer therefore needs to author a policy, keep editions, and see which mapped requirements still lack evidence. The first slice already owned one official control catalog. A second catalog or a policy-engine dialect would invent a competing truth.

Open Policy Agent Rego is a general-purpose authorization language. It does not replace documented ISMS policy text, and it does not bind evidence to CSAP / SOC 2 TSC / ISMS-P / ISO 27001 identifiers. It is out of scope for this slice.

## Decision

1. Store policies in 3NF as `policy_document` (stable identity), `policy_version` (immutable edition), and `policy_control_mapping` (edition → official `control_item` only).
2. Reject any mapping that is not already in the seeded catalog. Do not invent identifiers.
3. Treat a policy gap as a latest-edition mapping with zero `control_evidence_binding` rows. Reuse the existing evidence-binding model.
4. Expose authoring, gap listing, and evidence bind on HTTP and on the `cwl-grc` CLI. Customer copy states the next action.
5. Do not add a Rego/OPA PDP in this slice.

## Consequences

Officers can write a policy, see an uncovered mapped control, and attach the next evidence without leaving CWL GRC. Residual risk scoring and audit-workflow bodies remain later work. Peer CWL services still consume control/evidence contracts only.

## Citation alignment

The official COSO 2013 principles poster restates Principle 12 as deploying control activities through policies that establish what is expected and procedures that put those policies into action (Committee of Sponsoring Organizations of the Treadway Commission, 2013). That confirms the already-accepted policy-deployment rule; no new section numbers are added. ISO/IEC 27001:2022 clause 5.2 and Annex A A.5.1 remain as already written and are cited from the official ISO catalogue page for the 2022 edition; the public page does not republish paid clause text, and no RFC is required. AICPA SOC 2 CC5.3, KISA ISMS-P 1.1.5, and CSAP 1.1.1 likewise stay as already written and are cited from the official catalogue or notice pages. Open Policy Agent documents Rego as a declarative policy-evaluation language, not a versioned policy-document or evidence-binding store.

## References

American Institute of Certified Public Accountants. (2022). *2017 trust services criteria for security, availability, processing integrity, confidentiality, and privacy (with revised points of focus—2022)* (TSP Section 100). https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

Committee of Sponsoring Organizations of the Treadway Commission. (2013). *Internal control—Integrated framework*. https://www.coso.org/guidance-on-ic

International Organization for Standardization. (2022). *Information security, cybersecurity and privacy protection—Information security management systems—Requirements* (ISO/IEC 27001:2022). https://www.iso.org/standard/27001

Korea Internet & Security Agency. (2023, November 23). *정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서* [Information security and personal information management system (ISMS-P) certification criteria guide]. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlRcsrmDetail.do?searchRcsrmMngId=RCSRMID_000000010105

Korea Internet & Security Agency. (2026, July 6). *2026년 클라우드서비스 보안인증기준 해설서(2026.07)* [2026 cloud service security certification criteria commentary]. File corrected July 28, 2026. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlVrtlRcsrmList.do?rcsrmMenuCd=1003&searchKeyword=%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C%EC%84%9C%EB%B9%84%EC%8A%A4+%EB%B3%B4%EC%95%88%EC%9D%B8%EC%A6%9D%EA%B8%B0%EC%A4%80+%ED%95%B4%EC%84%A4%EC%84%9C

Open Policy Agent. (n.d.). *Policy language*. https://www.openpolicyagent.org/docs/latest/policy-language/
