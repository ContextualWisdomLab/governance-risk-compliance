# Governance, Risk & Compliance

CWL GRC is the ContextualWisdomLab product boundary for versioned policy, control, risk, evidence, and compliance-audit truth.

## Product responsibility

The product maps policies and evidence to governed control catalogs, preserves auditable version and evidence history, exposes coverage gaps, and supports risk and compliance workflows without turning another CWL product into the GRC system of record.

The current repository includes a developer-preview surface and active production-hardening work. Documentation, open pull requests, or local validation are not certification, production deployment, or attestation evidence.

## Start here

- [Repository README](../README.md) — current product workflow, integrity guarantees, and developer-preview boundary.
- [Product and technical gap baseline](product-technical-gap-baseline.md) — current readiness gaps and evidence state.
- [Architecture decisions](adr/) — accepted product, control, and integration decisions.
- [Standards and source references](doctoring/REFERENCES.md) — official catalog and standards references.
- [GitHub Releases](https://github.com/ContextualWisdomLab/governance-risk-compliance/releases) — immutable release artifacts when available.
- [Ask DeepWiki](https://deepwiki.com/ContextualWisdomLab/governance-risk-compliance) — repository-aware navigation and questions.

## Authority and ecosystem boundary

GRC owns policy, control, risk, evidence, audit, findings, remediation, exception, and compliance-domain truth. Identity, employment, accounting books, commercial metering, enterprise architecture, semantic models, and other product data remain authoritative in their owning bounded contexts and are consumed through reviewed contracts or evidence projections rather than cross-service application-table access.

Control catalogs such as CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001, NIST SP 800-53, and COSO are governed reference inputs. Their presence in the product does not imply certification or independent attestation.

## Security and release evidence

Production readiness requires authenticated identity and tenant/purpose authorization, durable evidence-key management, database and recovery controls, dependency and supply-chain evidence, operational telemetry, protected integration, and then-current review/security gates. Historical or predecessor check results are not transferred across source or base changes.

## Publication status

This file is a GitHub Pages source prerequisite, not proof that Pages is live. Publication is complete only after the reviewed source reaches the protected default branch, the organization-owned repository metadata reconciler applies the intended Pages configuration, deployment succeeds, and the public HTTPS content is re-read successfully.
