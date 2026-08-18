# ADR 0002: Control and evidence model

- Status: Draft
- Date: 2026-08-18

## Context

A GRC leaf must say what a control is, what evidence is, and how an officer sees
a gap. The model has to rest on current, named international instruments. A
local catalog invented on this documentation-only branch would not be those
instruments.

Three publications were opened on official publisher or government pages:

- NIST CSWP 29, *The NIST Cybersecurity Framework (CSF) 2.0*, 26 February 2024,
  DOI [10.6028/NIST.CSWP.29](https://doi.org/10.6028/NIST.CSWP.29)
- ISO/IEC 27001:2022, *Information security, cybersecurity and privacy
  protection — Information security management systems — Requirements*,
  25 October 2022, IEC publication
  [79694](https://webstore.iec.ch/en/publication/79694)
- AICPA 2017 Trust Services Criteria for Security, Availability, Processing
  Integrity, Confidentiality, and Privacy (with revised points of focus — 2022),
  official AICPA & CIMA download

NIST CSF 2.0 is a taxonomy of cybersecurity outcomes. It does not prescribe how
those outcomes are achieved. ISO/IEC 27001:2022 states ISMS requirements,
including risk assessment and treatment. The 2017 TSC (2022 points of focus)
are the control criteria used when a SOC 2® examination reports on security,
availability, processing integrity, confidentiality, or privacy.

## Decision

This leaf treats official control language as external authority and treats
bound evidence as the local proof that a named control is covered.

1. **Control.** A control identifier and statement come from a cited official
   catalog. This draft does not copy, number, or invent those items.
2. **Evidence.** An evidence record is an artifact an officer can attach to a
   control. An empty binding is a visible gap, not a silent pass.
3. **International grounding.** Product language for cybersecurity outcomes
   follows NIST CSF 2.0. Information-security management requirements follow
   ISO/IEC 27001:2022. SOC 2 examinations follow the AICPA 2017 TSC with 2022
   points of focus.
4. **Personal data.** Officer and user data required for authorized GRC work
   stay usable. Protection is purpose-bound access control, encryption, and
   audit. Masking is not the product rule.

ISO.org’s HTML catalog for standard 82875 was not retrieved in this environment
(Cloudflare challenge). The ISO/IEC title, designation, edition, and date are
taken from the IEC Webstore listing of the joint publication.

## Consequences

- A later implementation may map only identifiers that appear in the cited
  catalogs. Invented local codes are out of scope.
- CSF 2.0 outcomes are not themselves a control-item database. ISO/IEC 27001
  Annex A items and TSC criteria are not reproduced here.
- SOC 2® remains an examination that uses the TSC. This leaf does not claim a
  SOC 2 report exists.
- This draft adds no runtime, package, catalog database, or test harness.

## References

American Institute of Certified Public Accountants. (2022). *2017 Trust
Services Criteria for Security, Availability, Processing Integrity,
Confidentiality, and Privacy (with revised points of focus — 2022)*.
https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022

International Organization for Standardization & International Electrotechnical
Commission. (2022). *Information security, cybersecurity and privacy protection
— Information security management systems — Requirements* (ISO/IEC 27001:2022).
https://webstore.iec.ch/en/publication/79694

National Institute of Standards and Technology. (2024). *The NIST Cybersecurity
Framework (CSF) 2.0* (NIST Cybersecurity White Paper 29). U.S. Department of
Commerce. https://doi.org/10.6028/NIST.CSWP.29
