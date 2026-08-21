# Doctoring references

Official texts used for first-slice identifiers and authentication contracts. If a citation and the code conflict, fix the code.

American Institute of Certified Public Accountants. (2022). *2017 trust services criteria for security, availability, processing integrity, confidentiality, and privacy (with revised points of focus—2022)* (TSP Section 100). https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens* (RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068

Committee of Sponsoring Organizations of the Treadway Commission. (2013). *Internal control—Integrated framework*. https://www.coso.org/guidance-on-ic

Committee of Sponsoring Organizations of the Treadway Commission. (2017). *Enterprise risk management—Integrating with strategy and performance*. https://www.coso.org/_files/ugd/3059fc_61ea5985b03c4293960642fdce408eaa.pdf

International Organization for Standardization. (2022). *Information security, cybersecurity and privacy protection—Information security management systems—Requirements* (ISO/IEC 27001:2022). https://www.iso.org/standard/27001

Korea Internet & Security Agency. (2023, November 23). *정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서* [Information security and personal information management system (ISMS-P) certification criteria guide]. https://isms.kisa.or.kr/main/ispims/notice/?boardId=bbs_0000000000000014&mode=view&cntId=21

Korea Internet & Security Agency. (2026, July 6). *2026년 클라우드서비스 보안인증기준 해설서(2026.07)* [2026 cloud service security certification criteria commentary]. File corrected July 28, 2026. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlVrtlRcsrmList.do?rcsrmMenuCd=1003&searchKeyword=%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C%EC%84%9C%EB%B9%84%EC%8A%A4+%EB%B3%B4%EC%95%88%EC%9D%B8%EC%A6%9D%EA%B8%B0%EC%A4%80+%ED%95%B4%EC%84%A4%EC%84%9C

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current practice for OAuth 2.0 security* (RFC 9700, BCP 240). RFC Editor. https://www.rfc-editor.org/rfc/rfc9700

Open Policy Agent. (n.d.). *Policy language*. https://www.openpolicyagent.org/docs/latest/policy-language/

OpenID Foundation. (2023a). *OpenID Connect Core 1.0 incorporating errata set 2*. https://openid.net/specs/openid-connect-core-1_0-errata2.html

OpenID Foundation. (2023b). *OpenID Connect Discovery 1.0 incorporating errata set 2*. https://openid.net/specs/openid-connect-discovery-1_0-errata2.html

Ross, R., & Pillitteri, V. (2020). *Security and privacy controls for information systems and organizations* (NIST Special Publication 800-53 Rev. 5). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-53r5

Barker, E. (2020). *Recommendation for key management: Part 1—General* (NIST Special Publication 800-57 Part 1 Revision 5). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-57pt1r5

Policy authoring in this slice follows ISO/IEC 27001:2022 clause 5.2 (information security policy as documented information) and Annex A control A.5.1 (policies for information security); COSO (2013) Principle 12 and AICPA (2022) SOC 2 CC5.3 (deploy control activities through policies and procedures); KISA (2023) ISMS-P 1.1.5; and KISA (2026) CSAP 1.1.1. Open Policy Agent Rego was reviewed and not adopted: it is an authorization PDP language, not a policy-document or evidence-binding store.

The CSAP catalog stores the edition-specific KISA resource notice rather than the generic CSAP introduction page. A content digest is not claimed in this slice because the original attachment bytes were not independently captured and hashed in the repository; adding a digest requires an immutable source-artifact ingestion workflow and reviewable byte-level evidence.

The first Keyverse authentication prerequisite follows RFC 9068 for explicit JWT access-token typing, signed RS256 validation, issuer/audience checks, and required access-token claims; RFC 9700 for resource/action restriction and client-versus-resource-owner separation; and the OpenID Connect Core/Discovery errata-set-2 issuer and signing-key metadata semantics. Discovery and live JWK retrieval are intentionally deferred until URL pinning, redirect refusal, response bounds, cache/rotation, and issuer-outage behavior have executable tests.

The first evidence key-lifecycle slice follows NIST SP 800-57 Part 1 Revision 5 key-inventory, key-lifecycle, metadata-protection, and recovery principles. KMS/HSM integration, legal hold, retention disposition, backup, and restore rehearsal remain explicit follow-up work rather than unverified production claims.
