# ADR 0001: Control catalog and evidence binding as the first GRC slice

## Status

Accepted for the first buyer-facing product slice.

## Context

A compliance officer could not see which CSAP / SOC 2 / ISMS-P controls had evidence, nor attach the next artifact. The repository had only a customer README.

## Decision

Ship a modular FastAPI kernel that:

1. Seeds official identifiers from CSAP, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017.
2. Stores evidence under purpose-limited authorization and encrypts payloads at rest without masking PII.
3. Binds evidence to one official control and queries uncovered controls.
4. Exposes `/healthz` and runs standalone or as `create_app()`.

Rejected alternatives: a catalog-only spreadsheet (cannot bind). Policy authoring was later confirmed as part of this same slice; see ADR 0002.

## Consequences

Other CWL products can consume control/evidence HTTP contracts. Residual risk scoring and audit-workflow bodies remain later slices. Product CI is local to this repo and does not take org Security/OpenCode/Noema lanes.
