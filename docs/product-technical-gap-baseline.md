# Product and technical gap baseline

Snapshot: 2026-08-21, Asia/Seoul
Repository: `ContextualWisdomLab/governance-risk-compliance`  
Baseline source head: `17400a947fe2d51e61022031c7dc28f93152e18b`

This document is the current product and technical truth baseline. It separates
observed runtime or GitHub evidence from inferred gaps and proposed acceptance
work. A green local test run, a merged pull request, a catalog mapping, or a
readiness manifest is not a production or compliance certification.

## Executive outcome

The repository has a credible first buyer slice: an officer can author an
immutable, versioned policy, map it to seeded official external-requirement
identifiers, attach encrypted evidence, and query a preliminary uncovered list.
The product is not ready for remote customer use because identity, tenant
authorization, key recovery, release provenance, operational telemetry, and
stable production contracts remain incomplete.

The first slice also stops before the central enterprise-GRC distinction between
an external requirement, an organization-designed internal control, one deployed
implementation, a control test, and an effectiveness conclusion. Directly
binding evidence to `control_item` can prove artifact presence but cannot prove
that a control was implemented or operated effectively.

PR #32 stages the Issue #27 product-model correction on top of PR #31. Its
exact head has green Product #468, local 100% statement/branch and docstring
evidence, and real SQLite/PostgreSQL lifecycle probes. It remains unmerged and
has no independent formal approval; those facts are a release gate, not a
claim that the correction is already present on `develop`.

PR #33 stages the Issue #28 obligation-applicability correction on top of PR
#32. Its exact head `17400a947fe2d51e61022031c7dc28f93152e18b` has terminal
Product #32401019372 and Devin Review success, resolved CodeRabbit findings,
local 161-test 100% statement/branch and docstring evidence, and a fresh real
PostgreSQL 18 lifecycle/immutability probe. It remains unmerged and depends on
PR #32's protected independent-review gate; this evidence does not transfer to
`develop` until the stacked merge sequence completes.

The next production action is to integrate one verified Keyverse tenant and
actor through the existing policy/evidence flow and prove that the same boundary
holds for every read, write, export, audit event, background job, and stored
relationship. The next product-model action is issue #27: establish internal
control, implementation, testing, effectiveness, deficiency, and evidence-usage
truth before risk and audit workflows depend on the current catalog model.

The complete domain sequence is defined in
[`docs/product/grc-domain-completion-roadmap.md`](product/grc-domain-completion-roadmap.md).

## Evidence convention

- **Observed** means reproduced from the current checkout or a current GitHub
  API/check result.
- **Inferred** means a gap derived from the mission, ADRs, issue contracts, or
  an ownership boundary; it still needs implementation proof.
- **Proposed** means the smallest acceptance slice intended to turn the gap into
  an observable product capability.

## Automation status

No repository workflow on `develop` currently declares an hourly `schedule`
trigger, and no authenticated contextual-orchestrator scheduler executor is
available in this environment. No placeholder automation was added. The next
automation action is to use an approved central scheduler identity for the
protected PR queue, exact-head checks, independent review, and safe handoff
evidence rather than duplicating a privileged loop in this repository.

## Current product contract

| Capability | Observed implementation | Boundary that still matters |
| --- | --- | --- |
| Policy authoring | `policy_document`, immutable `policy_version`, and `policy_control_mapping`; HTTP and CLI paths exist. | No approval/publication workflow, effective period, scheduled review, or tenant-backed identity. |
| External-requirement catalogs | CSAP 2026.07, SOC 2 TSC, ISMS-P, ISO/IEC 27001:2022, NIST SP 800-53 Rev. 5, COSO 2013, and COSO 2017 identifiers are seeded. | The catalog is a small checked-in slice, not a licensed source-artifact ingestion, edition-diff, OSCAL, or OLIR service. |
| Requirement/control semantics | PR #32 stages separate objectives, versioned internal-control definitions, scoped implementations, reviewed mappings, design/operating tests, deficiencies, exceptions, and evidence usage; direct bindings project to `unassessed`. | PR #32 is stacked and unmerged; stable authenticated APIs, production identity, and downstream risk/audit consumers remain incomplete. |
| Compliance applicability | PR #33 stages tenant-scoped source revisions, obligations, jurisdictions, applicability decisions, commitments, regulatory changes, impact assessments, and overdue/upcoming worklists; exact-head Product and PostgreSQL evidence is recorded above. | PR #33 is stacked and unmerged; production Keyverse authorization, stable versioned APIs, external source ingestion, and downstream risk/audit workflows remain incomplete. |
| Evidence | Evidence is encrypted at rest, exact operational values remain usable, and artifacts bind to catalog rows. | Rotation, KMS/HSM, recovery rehearsal, disposition, request/review workflow, purpose-specific exports, and tenant authorization are incomplete. |
| Gap query | PR #32 projects latest policy mappings and catalog rows through explicit control statuses; legacy direct bindings remain `unassessed`. | The feature is not merged, and risk priority, production ownership, authenticated APIs, and remediation workflows remain absent. |
| Integrity | SQLite/PostgreSQL triggers protect audit history and finalized policy history; stale policy writers receive `409 Conflict`. | PostgreSQL lifecycle work is in PR #18 and is not merged at this snapshot. |
| Runtime boundary | The HTTP server is loopback-only; `X-Actor-Id` and `X-Purpose` are explicitly non-authenticating declarations. | No production remote deployment is permitted until Keyverse identity, tenant authorization, and deployment hardening close the trust boundary. |
| Module boundary | `create_app()` and the `cwl_grc` package support standalone or imported use. | Authenticated versioned service contracts and cross-repository contract tests do not yet exist. |
| Quality | Product workflows require locked dependencies, lint, docstrings, compile, and 100% statement/branch coverage. | Passing quality gates proves code quality only for the tested scope; it does not establish product completeness, effectiveness, or certification. |

Authoritative first-slice decisions are in
[ADR 0001](adr/0001-control-evidence-first-slice.md) and
[ADR 0002](adr/0002-policy-versioning-official-controls.md). The product-model
separation is proposed in
[ADR 0011](adr/0011-separate-external-requirements-and-internal-controls.md).
The implementation remains a modular kernel, not a monolith that absorbs
identity, employment, architecture, data catalog, billing, communications, or
organization-wide security scanning.

## Buyer-visible gap register

`G-*` identifiers are product-analysis identifiers in this document. They are
not GitHub issue numbers, control identifiers, certifications, or release gates.
One implementation issue may address several gaps, and a gap may require several
issues and PRs.

| ID | Priority | Buyer-visible gap | Current evidence | Proposed acceptance slice | Authority |
| --- | --- | --- | --- | --- | --- |
| G-01 | P0 | A customer cannot safely use the product remotely because caller identity and tenant are not verified. | Local-only boundary in `cwl_grc/remote_access.py`; issue #4; PRs #5, #6, #7, and #16 are the staged Keyverse work. | Verify issuer, audience, token type, signature, actor, tenant, workspace, client, principal kind, role, purpose, and action scope on every protected read/write/export/background job. | [Issue #4](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/4) |
| G-02 | P0 | Operators can encounter ambiguous schema ownership or migration failure in durable PostgreSQL deployments. | PR #18 implements the first schema-lifecycle slice, including explicit ownership, compatibility checks, PostgreSQL acceptance, and review fixes. | Merge only after fresh exact-head Product, PostgreSQL, SAST, Security, semantic review, zero valid unresolved findings, and live branch-policy evidence. | [Issue #8](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/8) |
| G-03 | P0 | Loss, rotation, retention, legal hold, or recovery failure can make exact operational evidence unavailable or non-compliant. | PR #20 adds versioned key metadata and bounded rewrap; PR #21 adds retention and tenant-scoped legal-hold transitions. Both are stacked and unmerged. | Add production KMS/HSM, durable rewrap receipts, disposition, purpose-specific disclosure, encrypted backup, PITR, restore verification, RPO/RTO, and emergency read-only operation. | [Issue #9](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/9) |
| G-04 | P0 | A buyer cannot independently verify that a released artifact came from reviewed source or can be rolled back safely. | No signed production OCI/wheel release, artifact-bound SBOM/provenance, protected promotion, or revocation rehearsal is merged. | Build immutable signed artifacts, verify the exact security result, promote by digest, enforce rulesets, and rehearse install/upgrade/rollback/revocation. | [Issue #10](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/10) |
| G-05 | P0 | Operators lack merged readiness, telemetry, SLO, alerting, and incident evidence. | `develop` still exposes the first-slice constant `/healthz`; PRs #22–#26 and #31 stage readiness, request/database/pool/recovery telemetry and a proposed SLO policy. | Complete collector delivery, recording rules, dashboards, burn-rate paging, recovery coordinator, service-owner approval, rollback/restore rehearsal, and production integration evidence. | [Issue #11](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/11) |
| G-06 | P1 | Consumers cannot safely depend on a stable production API or bounded resource behavior. | Routes are unversioned, broad dictionaries remain, list APIs are unpaginated, mutations lack a complete idempotency contract, and errors are endpoint-specific. | Add `/v1`, strict models, cursor pagination, idempotency, ETags/preconditions, RFC 9457 errors, bounded media/size/time/concurrency, OpenAPI security, fuzz/property and consumer-contract tests. | [Issue #12](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/12) |
| G-07 | P1 | The product cannot register, assess, treat, accept, monitor, and close risk through reviewed control-effectiveness truth. | No risk register or methodology exists; issue #13 now explicitly depends on internal-control implementation and test truth from #27. | Add immutable methodology-versioned inherent/residual assessments, appetite/tolerance, treatment, time-bounded acceptance, reviews, indicators, escalation, and non-duplicated mitigation. | [Issue #13](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/13) |
| G-08 | P1 | An auditor cannot run a complete governed audit from program planning through independent closure. | Evidence and `audit_event` exist, but audit universe, program, engagement, procedures, sampling, workpapers, findings, competence, independence, supervision, remediation, retest, closure, and quality assessment do not. | Implement the ISO 19011:2026 and IIA-aligned workflow against actual internal-control implementations and purpose-bound evidence usage. | [Issue #14](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/14) |
| G-09 | P0 | A green workflow can be mistaken for release authority without one exact machine-verifiable readiness decision. | PR #17 adds a fail-closed readiness manifest and repository-file evidence binding; it remains unmerged and intentionally reports `production_ready=false`. | Require exact current source/artifact evidence, freshness, branch policy, security gates, independent approval, and zero blockers before release mode succeeds. | [Issue #15](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/15) |
| G-10 | P1 | Catalog maintenance can drift, lose provenance, overstate mappings, or redistribute source text without authority. | Catalog rows are manually checked into `cwl_grc/catalog.py`; release identity, source digest, parser receipt, license policy, deterministic diff, reviewed crosswalk, OSCAL, and OLIR are absent. | Add lawful source-artifact ingestion, versioned release/diff, export restrictions, OSCAL 1.2.3 Catalog/Profile/Mapping round trips, reviewed mapping semantics, OLIR provenance, and change impact. | [Issue #29](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/29) |
| G-11 | P1 | A buyer lacks a role-aware compliance workspace, evidence request room, external-auditor data room, and controlled export. | The officer HTML is a loopback preview; saved views, exact-value reporting, export receipts, revocation, Figma, design tokens, Storybook, WCAG 2.2, print/PDF, and i18n evidence are absent. | Deliver tenant- and purpose-scoped posture, traceability, evidence requests, action queues, accessible exact-value views, reproducible CSV/JSON/PDF exports, and expiring/revocable auditor packages. | [Issue #30](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/30) |
| G-12 | P1 | Cross-repository consumers cannot rely on a governed GRC contract. | Architecture names Keyverse, Orgmetra, AIS, Billing, naruon, EA, and Semantic Data Portal as future consumers or authorities only. | Publish minimal OpenAPI/event contracts, opaque references, purpose/tenant/provenance envelopes, contract tests, and explicit authoritative/observed/inferred/proposed boundaries. | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| G-13 | P0 | External requirements, internal controls, implementations, tests, and evidence use are conflated. | PR #32 exact head `138c8331723785d7188c4f5403cff61a1d9e9f40` stages the separated model, migration backfill, explicit statuses, SQLite/PostgreSQL guards, Product #468 success, and real PostgreSQL 18 probe; no independent approval or protected merge is observed. | Re-fetch PR #32 exact head after review, resolve valid findings, obtain independent approval, merge through branch protection, and then integrate authenticated stable APIs before risk/audit consumers depend on the model. | [Issue #27](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/27) |
| G-14 | P1 | The product cannot prove which laws, regulations, contracts, and commitments apply to a precise tenant, scope, jurisdiction, and time. | PR #33 exact head `17400a947fe2d51e61022031c7dc28f93152e18b` stages source revisions, obligations, jurisdiction references, applicability decisions, legal interpretations, commitments, source changes, impact assessments, tenant checks, immutable guards, exact-head Product/Devin evidence, and a PostgreSQL 18 probe; no protected merge is observed. | Complete the protected PR #32 → PR #33 merge sequence, then add production Keyverse authorization, lawful source-artifact ingestion/diff, stable authenticated APIs, and downstream risk/audit/workspace consumers. | [Issue #28](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/28) |

## Current open-issue snapshot

Snapshot inclusion rule: every GitHub issue returned as open for this repository
on 2026-08-20. Pull requests are excluded and listed separately below. All 13
entries were open at the snapshot; their state can change after this commit.

| Issue | Snapshot state | Primary gap / purpose |
| --- | --- | --- |
| [#4](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/4) | Open | G-01 — Keyverse identity and tenant authorization |
| [#8](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/8) | Open | G-02 — PostgreSQL schema lifecycle |
| [#9](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/9) | Open | G-03 — evidence key, retention, legal hold, and recovery |
| [#10](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/10) | Open | G-04 — signed release and protected promotion |
| [#11](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/11) | Open | G-05 — readiness, telemetry, SLO, and incident operations |
| [#12](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/12) | Open | G-06 — versioned API, concurrency, and abuse controls |
| [#13](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/13) | Open | G-07 — risk register, treatment, and acceptance |
| [#14](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/14) | Open | G-08 — audit program, findings, remediation, and closure |
| [#15](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/15) | Open | G-09 — machine-verifiable readiness evidence gate |
| [#27](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/27) | Open | G-13 — separate external requirements and internal controls |
| [#28](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/28) | Open | G-14 — obligation, applicability, and regulatory change |
| [#29](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/29) | Open | G-10 — catalog governance, OSCAL, and OLIR |
| [#30](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/30) | Open | G-11 — buyer workspace, evidence room, and exports |

## Current pull-request queue

Snapshot inclusion rule: every open pull request except PR #19, which is the
branch carrying this baseline and is described after the table. Every row below
uses the full 40-character head SHA observed on 2026-08-20. A later push makes
that row stale and requires a new snapshot. No self-approval, admin merge,
force-push, or predecessor-head evidence is valid.

| PR | Exact head at snapshot | State | Current evidence/action |
| --- | --- | --- | --- |
| [#18](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/18) | `bc47c10fe8f996a1c51dc1edbdc313454ecfa879` | Ready, mergeable, blocked | Current head includes PostgreSQL acceptance cleanup and statement-time trigger assertions. Local full coverage and real PostgreSQL acceptance were reported; current exact-head external gates and independent approval remain merge requirements. |
| [#17](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/17) | `d42928e127c09a11d3aecba9ded35f5c6bbcc7a2` | Ready, mergeable, review-required | Product, Production Readiness, SAST, and Security runs were previously observed green on this head, but no independent formal approval was observed. Keep the readiness result intentionally false. |
| [#20](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/20) | `834868d4a6118bb0eeed3079e0c1407bf61303e0` | GitHub Ready metadata; semantically stacked | Body describes the first #9 key-lifecycle slice as Draft and dependent on #16, but GitHub metadata is non-draft. Restore Draft or otherwise prevent out-of-order merge; retain KMS, recovery, retention, legal-hold, and export gaps. |
| [#21](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/21) | `9ddabe8cffde7d97d3762403d8988b8d6ca970ef` | GitHub Ready metadata; semantically stacked | Body describes retention/legal hold as Draft and stacked on #20, but GitHub metadata is non-draft. Restore Draft or otherwise prevent out-of-order merge; disposition and recovery remain open. |
| [#22](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/22) | `47be55018da565fc34d4ab8f9afb6053dd7eba3b` | Ready, stacked, review-required | Operational readiness slice stacked on #21. Product evidence exists for the slice; parent integration, full exact-head security/review requirements, telemetry, and remote-boundary work remain. |
| [#23](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/23) | `fac1c0017aaeefcc4a6d966cbdfbe05e1b2163d4` | Ready, stacked, review-required | Request telemetry stacked on #22. Collector acceptance, database/pool/recovery metrics, SLO, paging, restore/rollback, parent integration, and independent approval remain. |
| [#24](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/24) | `84c12650347637dea849d1fe6d6f7d9a020e7799` | Ready, stacked, review-required | Database transaction telemetry stacked on #23. Pool/recovery signals, collector acceptance, SLO, paging, recovery rehearsal, parent integration, and independent approval remain. |
| [#25](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/25) | `a62d66e5ce3efedf27b11a8cae689db85989587d` | Ready, stacked, review-required | Proposed SLO/error-budget policy stacked on #24. Service-owner approval, collector delivery, recording rules, dashboards, paging, recovery rehearsal, and exact-head acceptance remain. |
| [#26](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/26) | `7564e175eb1d8bd9797184583cb681a5aa2225a6` | Ready, stacked, review-required | Bounded database-pool telemetry stacked on #25. Product run #442 is terminal-success on the exact head; no other workflow run was returned for that head, and independent approval remains unobserved. |
| [#31](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/31) | `2e34c86b9a0c20fade2b6b67c1e472fa599228d2` | Ready, stacked, review-required | Declared recovery-event telemetry stacked on #26. Product run #450 is terminal-success on the exact head; the PR expressly excludes a recovery coordinator, collector, dashboards, paging, rehearsal, owner approval, and production recovery evidence. |
| [#32](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/32) | `138c8331723785d7188c4f5403cff61a1d9e9f40` | Ready, stacked, review-required | Internal-control model stacked on #31 for Issue #27. Product run #468 is terminal-success on the exact head; local and PostgreSQL evidence is recorded, but CodeRabbit skips non-default base branches and no independent formal approval or protected merge is observed. |
| [#33](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/33) | `17400a947fe2d51e61022031c7dc28f93152e18b` | Ready, stacked, review-required | Obligation applicability and regulatory-change model stacked on #32 for Issue #28. Product run #32401019372 and Devin Review are terminal-success on the exact head; local 161-test/100% evidence, PostgreSQL 18 lifecycle/immutability evidence, and resolved CodeRabbit findings are recorded. Keep unmerged until PR #32 independently approves and protected merge completes. |
| [#16](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/16) | `c1496be499473befc273ff55ea284ac9f5582b73` | Draft, mergeable | Tenant isolation remains stacked behind #7. Preserve the shared official catalog outside tenant-owned records; regenerate all current-head gates after parent integration. |
| [#7](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/7) | `ebac50ccbb9cf528044cc53d4832ceec176b50c9` | Draft, mergeable | Route enforcement remains stacked behind #6. Revalidate every protected route and scope on the integrated parent. |
| [#6](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/6) | `887f5c64843cca5cd8f699cae58e33afa3b7498f` | Draft, mergeable | OIDC/JWKS loading remains stacked behind #5. Preserve bounded source retrieval, exact issuer matching, address pinning, TLS identity, and rotation semantics. |
| [#5](https://github.com/ContextualWisdomLab/governance-risk-compliance/pull/5) | `0c9c2525918f0f392185942065920c376ef9de28` | Ready, mergeable, review-required | JWT verification is the first direct-to-`develop` security slice. Fresh exact-head Product, SAST, Security, semantic review, branch policy, and independent approval remain required; predecessor evidence does not transfer. |

PR #19 carries this snapshot on branch `docs/product-technical-gap-baseline`.
It is not its own production, issue-completion, or merge approval.

The current branch endpoint reports `develop` as `protected: true`, but its
returned protection object has `enabled: false`, required-status-check
enforcement `off`, and empty required contexts/checks. This is an observed
repository-governance gap, not permission to bypass checks or independent
review. Confirm and enforce the organization ruleset through the authorized
control plane before merging or releasing.

## Technical architecture and ownership gaps

```mermaid
flowchart LR
    officer[Authorized GRC user] --> grc[CWL GRC kernel]
    source[Authoritative source and revision] --> obligation[Obligation and applicability]
    obligation --> requirement[External requirement catalog]
    requirement --> policy[Versioned policy]
    policy --> internal_control[Internal-control definition]
    internal_control --> implementation[Scoped implementation]
    implementation --> test[Control test and effectiveness]
    test --> evidence[Encrypted evidence and purpose-bound usage]
    implementation --> risk[Risk assessment and treatment]
    test --> audit_program[Audit program, finding, and retest]
    risk --> remediation[Remediation or acceptance]
    audit_program --> remediation
    remediation --> workspace[Buyer workspace and controlled export]
    grc --> audit_event[Append-only application audit events]
    keyverse[Keyverse identity and tenant] -. required trust boundary .-> grc
    release[Signed artifact and provenance] -. release gate .-> grc
```

GRC owns obligation/applicability decisions, policies, external-requirement
references, internal controls, implementations, tests, evidence usage, risk,
GRC audit, remediation, and GRC reporting truth. Keyverse owns identity and
authorization. Central security workflows own scanners. Other products retain
people, architecture, data, billing, and communication truth and expose
versioned references. Inferred relationships from AI or lineage products remain
`inferred` or `proposed` until an authorized GRC review changes their status.

Database acceptance remains 3NF by default. New database objects use at least
two-word `snake_case`, tenant consistency at the database boundary, immutable or
superseded history, and distinct business-valid/system-recorded time where
reconstruction matters. Before high-volume `audit_event`, evidence-usage,
telemetry, workflow, or export tables are introduced, define and test indexing,
partitioning, retention, and hot-partition behavior. No current evidence proves
the future enterprise workload is partitioned or load-tested.

## Standards and doctoring actions

The doctoring baseline now includes:

- ISO 37301:2021, confirmed current in 2026, and Amendment 1:2024 for compliance
  management and obligation framing;
- ISO 19011:2026 Edition 4, replacing withdrawn ISO 19011:2018 for
  management-system audit guidance;
- NIST OSCAL 1.2.3 model documentation, including Catalog, Profile, Control
  Mapping, Component Definition, SSP, Assessment Plan, Assessment Results, and
  POA&M models; and
- the NIST OLIR Program for versioned informative-reference mappings.

NIST issued final SP 800-53 Release 5.2.0 on August 27, 2025. It adds and
revises controls, enhancements, discussions, related controls, references, and
corresponding assessment procedures. The checked-in `nist_sp_800_53_r5` rows are
a manually authored first-slice subset based on the 2020 Rev. 5 catalog; they
have not been refreshed, diffed, or proven complete against Release 5.2.0.
Issue #29 must ingest an exact lawful artifact, preserve its digest and import
receipt, compute the reviewed change set, and decide whether to retain the
framework key or introduce a release-specific identity before the product
claims a 5.2.0 catalog baseline.

Catalog ingestion must consume authoritative source artifacts and preserve exact
release, digest, parser receipt, publisher, mapping status, and license/export
policy. Search results, generated summaries, or LLM proposals cannot become
source truth. ISO and other licensed publications must not be copied, transformed,
or exported without recorded authority. Supporting an identifier, crosswalk, or
OSCAL adapter does not establish conformance or certification.

Figma and Storybook are not claimed for the current first-slice UI. Before a
customer-facing component system is introduced, ADR work under #30 must record
the Figma file ID, design tokens, Storybook inventory, accessibility and exact-
value-table behavior, keyboard/touch action edges, print/PDF, responsive states,
i18n consistency, and ownership boundaries.

## Verification loop

1. Re-fetch each PR’s exact head, base, checks, reviews, and unresolved threads.
2. Fix valid findings at the shared root and add a realistic regression test for
   every non-trivial security, parser, concurrency, data-integrity, temporal,
   authorization, or workflow rule.
3. Run `git diff --check` against the entire exact-head PR diff, then run locked
   Product, docstring, compile, PostgreSQL, contract, SAST, Security,
   semantic-review, accessibility, and applicable end-to-end gates on that same
   unchanged head.
4. Confirm independent approval and the live organization ruleset; merge only
   through the protected path and expected head.
5. After each merge, advance the next stacked PR only if its ownership boundary
   remains correct; regenerate all exact-head evidence rather than transferring
   predecessor results.
6. Update this baseline, the domain roadmap, ADRs, doctoring, README, CHANGELOG,
   readiness manifest, and issue dependencies whenever current truth changes.
7. When the active queue is empty, select the highest buyer-visible gap whose
   prerequisites are satisfied and ship one complete vertical slice rather than
   producing a disconnected scaffold.

## Product status

The repository remains a loopback-only developer preview until G-01 through
G-05 have current production evidence and G-09 succeeds under independent
release authority. It must not be described as a remote-ready service.

Even after remote exposure becomes safe, the repository is not a completed
enterprise GRC product until G-13 establishes internal-control and effectiveness
truth and the dependent obligation, risk, audit, interoperability, remediation,
and buyer-workspace loops are implemented and evidenced. No document, score,
mapping, green CI run, or export in this repository should be presented as a
compliance certification.
