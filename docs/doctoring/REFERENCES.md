# Doctoring references

Official texts used for first-slice identifiers. If a citation and the code conflict, fix the code.

American Institute of Certified Public Accountants. (2022). *2017 trust services criteria for security, availability, processing integrity, confidentiality, and privacy (with revised points of focus—2022)* (TSP Section 100). https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

Committee of Sponsoring Organizations of the Treadway Commission. (2013). *Internal control—Integrated framework*. https://www.coso.org/guidance-on-ic

Committee of Sponsoring Organizations of the Treadway Commission. (2017). *Enterprise risk management—Integrating with strategy and performance*. https://www.coso.org/_files/ugd/3059fc_61ea5985b03c4293960642fdce408eaa.pdf

International Organization for Standardization. (2022). *Information security, cybersecurity and privacy protection—Information security management systems—Requirements* (ISO/IEC 27001:2022). https://www.iso.org/standard/27001

Korea Internet & Security Agency. (2023, November 23). *정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서* [Information security and personal information management system (ISMS-P) certification criteria guide]. https://isms.kisa.or.kr/main/ispims/notice/?boardId=bbs_0000000000000014&mode=view&cntId=21

Korea Internet & Security Agency. (2026, July 6). *2026년 클라우드서비스 보안인증기준 해설서(2026.07)* [2026 cloud service security certification criteria commentary]. File corrected July 28, 2026. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlVrtlRcsrmList.do?rcsrmMenuCd=1003&searchKeyword=%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C%EC%84%9C%EB%B9%84%EC%8A%A4+%EB%B3%B4%EC%95%88%EC%9D%B8%EC%A6%9D%EA%B8%B0%EC%A4%80+%ED%95%B4%EC%84%A4%EC%84%9C

Open Policy Agent. (n.d.). *Policy language*. https://www.openpolicyagent.org/docs/latest/policy-language/

Ross, R., & Pillitteri, V. (2020). *Security and privacy controls for information systems and organizations* (NIST Special Publication 800-53 Rev. 5). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-53r5

Fielding, R., Nottingham, M., & Reschke, J. (Eds.). (2022). *HTTP semantics* (RFC 9110). RFC Editor. https://www.rfc-editor.org/rfc/rfc9110.html

Fielding, R., Nottingham, M., & Reschke, J. (Eds.). (2022). *HTTP caching* (RFC 9111). RFC Editor. https://www.rfc-editor.org/rfc/rfc9111.html

Nottingham, M., Wilde, E., & Dalal, S. (2023). *Problem details for HTTP APIs* (RFC 9457). RFC Editor. https://www.rfc-editor.org/rfc/rfc9457.html

Policy authoring in this slice follows ISO/IEC 27001:2022 clause 5.2 (information security policy as documented information) and Annex A control A.5.1 (policies for information security); COSO (2013) Principle 12 and AICPA (2022) SOC 2 CC5.3 (deploy control activities through policies and procedures); KISA (2023) ISMS-P 1.1.5; and KISA (2026) CSAP 1.1.1. Open Policy Agent Rego was reviewed and not adopted: it is an authorization PDP language, not a policy-document or evidence-binding store.

The CSAP catalog stores the edition-specific KISA resource notice rather than the generic CSAP introduction page. A content digest is not claimed in this slice because the original attachment bytes were not independently captured and hashed in the repository; adding a digest requires an immutable source-artifact ingestion workflow and reviewable byte-level evidence.

The version-one HTTP contract uses RFC 9457 problem details and the
`application/problem+json` media type, and uses RFC 9110 conditional-request
semantics for `ETag`/`If-Match`. RFC 9111 caching guidance informed the choice
to keep the policy ETag representation-specific and strong. These references
define HTTP interoperability; they do not provide authentication, tenant
authorization, or a general idempotency standard. Those remain explicit
Keyverse and product-contract work.
