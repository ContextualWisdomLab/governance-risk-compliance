# Doctoring references

Official texts used for first-slice identifiers and product-completion decisions. If a citation and the code conflict, fix the code. A reference records provenance; it does not authorize copying licensed source text or claiming certification.

American Institute of Certified Public Accountants. (2022). *2017 trust services criteria for security, availability, processing integrity, confidentiality, and privacy (with revised points of focus—2022)* (TSP Section 100). https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

Committee of Sponsoring Organizations of the Treadway Commission. (2013). *Internal control—Integrated framework*. https://www.coso.org/guidance-on-ic

Committee of Sponsoring Organizations of the Treadway Commission. (2017). *Enterprise risk management—Integrating with strategy and performance*. https://www.coso.org/_files/ugd/3059fc_61ea5985b03c4293960642fdce408eaa.pdf

International Organization for Standardization. (2021). *Compliance management systems—Requirements with guidance for use* (ISO 37301:2021). https://www.iso.org/standard/75080.html

International Organization for Standardization. (2024). *Compliance management systems—Requirements with guidance for use—Amendment 1: Climate action changes* (ISO 37301:2021/Amd 1:2024). https://www.iso.org/standard/88422.html

International Organization for Standardization. (2026). *Guidelines for auditing management systems* (ISO 19011:2026, 4th ed.). https://www.iso.org/standard/19011

International Organization for Standardization. (2022). *Information security, cybersecurity and privacy protection—Information security management systems—Requirements* (ISO/IEC 27001:2022). https://www.iso.org/standard/27001

Korea Internet & Security Agency. (2023, November 23). *정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서* [Information security and personal information management system (ISMS-P) certification criteria guide]. https://isms.kisa.or.kr/main/ispims/notice/?boardId=bbs_0000000000000014&mode=view&cntId=21

Korea Internet & Security Agency. (2026, July 6). *2026년 클라우드서비스 보안인증기준 해설서(2026.07)* [2026 cloud service security certification criteria commentary]. File corrected July 28, 2026. https://isms-p.or.kr/ntcn/rcsrm/selectGnrlVrtlRcsrmList.do?rcsrmMenuCd=1003&searchKeyword=%ED%81%B4%EB%9D%BC%EC%9A%B4%EB%93%9C%EC%84%9C%EB%B9%84%EC%8A%A4+%EB%B3%B4%EC%95%88%EC%9D%B8%EC%A6%9D%EA%B8%B0%EC%A4%80+%ED%95%B4%EC%84%A4%EC%84%9C

National Institute of Standards and Technology. (n.d.). *National Online Informative References Program*. https://csrc.nist.gov/Projects/olir

National Institute of Standards and Technology. (n.d.). *Open Security Controls Assessment Language model documentation* (Version 1.2.3). https://pages.nist.gov/OSCAL-Reference/models/

National Institute of Standards and Technology. (2025, August 27). *Security and privacy controls for information systems and organizations: Release 5.2.0* (NIST SP 800-53 Rev. 5). https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

National Institute of Standards and Technology. (2025, August 27). *Summary of changes: NIST SP 800-53 Release 5.2.0*. https://csrc.nist.gov/files/projects/Risk-Management/800-53%20Comment%20Site/SP800-53-r5.2.0-changes.pdf

Open Policy Agent. (n.d.). *Policy language*. https://www.openpolicyagent.org/docs/latest/policy-language/

Ross, R., & Pillitteri, V. (2020). *Security and privacy controls for information systems and organizations* (NIST Special Publication 800-53 Rev. 5). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-53r5

Policy authoring in the first slice follows ISO/IEC 27001:2022 clause 5.2 (information security policy as documented information) and Annex A control A.5.1 (policies for information security); COSO (2013) Principle 12 and AICPA (2022) SOC 2 CC5.3 (deploy control activities through policies and procedures); KISA (2023) ISMS-P 1.1.5; and KISA (2026) CSAP 1.1.1. Open Policy Agent Rego was reviewed and not adopted: it is an authorization PDP language, not a policy-document or evidence-binding store.

The product-completion baseline uses ISO 37301:2021, confirmed current in 2026, for compliance-obligation and compliance-management-system framing. ISO 19011:2026 replaces the withdrawn ISO 19011:2018 baseline for management-system audit guidance; ISO 19011 provides guidance and does not itself provide certification. OSCAL 1.2.3 is the current machine-readable model baseline for catalog, profile, control mapping, component definition, system security plan, assessment plan, assessment results, and plan-of-action-and-milestones interoperability. OLIR mappings retain their own publisher, version, draft/final status, and provenance and are not automatically authoritative CWL decisions.

The checked-in `nist_sp_800_53_r5` first-slice rows were authored against the 2020 Rev. 5 catalog and have not been refreshed or proven complete against final Release 5.2.0. NIST issued Release 5.2.0 on August 27, 2025 with new and revised controls, enhancements, discussions, related controls, references, and corresponding assessment-procedure updates. Issue #29 must ingest a lawfully acquired exact release artifact, preserve its digest and import receipt, compute a reviewed edition diff, and decide whether the framework key remains compatible or requires a new release-specific identity before the catalog baseline is described as 5.2.0.

The CSAP catalog stores the edition-specific KISA resource notice rather than the generic CSAP introduction page. A content digest is not claimed in the first slice because the original attachment bytes were not independently captured and hashed in the repository; adding a digest requires an immutable source-artifact ingestion workflow and reviewable byte-level evidence.

ISO publications and other licensed standards remain subject to publisher copyright and usage restrictions. Public CWL records should use official identifiers, lawful source references, and independently authored summaries unless redistribution rights for source text are explicitly recorded.