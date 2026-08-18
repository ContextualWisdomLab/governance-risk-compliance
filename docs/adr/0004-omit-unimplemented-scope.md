# ADR 0004: Omit unimplemented scope

- Status: Draft
- Date: 2026-08-18

## Context

The default branch of this repository is documentation and a customer README.
There is no shipped runtime, installable package, control catalog database, or
test harness on that branch. Writing those artifacts in a documentation-only
change would invent product surface that officers cannot actually run.

Open implementation work already exists on a separate branch and must not be
stacked here.

## Decision

This documentation set describes authority, the control/evidence model, and
named official catalogs. It does not add:

- a web or CLI runtime
- a Python or other installable package
- a stored control-item or evidence database
- a test harness, coverage gate, or CI workflow that pretends those exist

A later reviewed slice may introduce those things. Until then, the customer
README keeps the honest operator line: attach evidence to empty CSAP / SOC 2 /
ISMS-P controls when a product slice lands.

Sibling repositories are not required to open, build, or read these drafts.

## Consequences

- Officers are not told to install or serve a product that this branch does not
  contain.
- Merge of this draft does not race an implementation pull request on package
  layout or catalog schema.
- Future slices must cite the official sources in
  [`../REFERENCES.md`](../REFERENCES.md) instead of treating these ADRs as a
  substitute catalog.

## References

ContextualWisdomLab. (2026). *Governance, Risk & Compliance* [Default-branch
tree: customer README only].
https://github.com/ContextualWisdomLab/governance-risk-compliance/tree/develop

National Institute of Standards and Technology. (2024). *The NIST Cybersecurity
Framework (CSF) 2.0* (NIST Cybersecurity White Paper 29). U.S. Department of
Commerce. https://doi.org/10.6028/NIST.CSWP.29
