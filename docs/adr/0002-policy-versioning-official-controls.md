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
