# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. This slice owns versioned policies, the official control catalog, evidence artifacts, control–evidence bindings, uncovered policy/control queries, and the Issue #14 audit program, engagement, finding, remediation, retest, and closure records.

```mermaid
flowchart LR
    officer[Compliance officer] --> home[Officer home /]
    officer --> api[Policy, control, and evidence API]
    officer --> cli[cwl-grc CLI]
    home --> preview[Local-only developer preview boundary]
    api --> preview
    preview --> kernel[cwl_grc kernel]
    cli --> kernel
    probe[/healthz] --> preview
    kernel --> policy[(policy_document / policy_version / policy_control_mapping)]
    kernel --> catalog[(control_framework / control_item)]
    kernel --> evidence[(evidence_record)]
    kernel --> binding[(control_evidence_binding)]
    kernel --> audit[(audit_event)]
    officer --> auditapi[Audit program, engagement, and finding API]
    auditapi --> preview
    kernel --> auditprogram[(audit_program / audit_engagement / engagement_criterion)]
    kernel --> auditteam[(engagement_team_member / independence_declaration)]
    kernel --> auditwork[(audit_procedure / audit_sample_item / audit_evidence_link)]
    kernel --> auditfinding[(audit_finding / audit_finding_revision)]
    kernel --> remediation[(remediation_action / finding_retest / finding_closure)]
    auditprogram --> catalog
    auditwork --> evidence
    remediation --> evidence
    keyverse[Keyverse OIDC / tenant authorization] -. required before remote deployment .-> preview
    consumers[Orgmetra / Keyverse / AIS / Billing / naruon / EA / SDP] -. future authenticated contracts .-> api
```

## Runtime layers

1. **Officer home**: buyer-oriented HTML that authors a policy, lists policy gaps, and attaches the next evidence in a local preview.
2. **HTTP API**: policy author/revise/list, policy-gap query, catalog list, uncovered query, evidence create, evidence bind, audit program/engagement/finding/remediation routes, overdue-remediation query, `/healthz`.
3. **Preview network boundary**: always rejects proxy-forwarded and non-loopback traffic; no runtime override exists before Keyverse authentication.
4. **CLI tools**: executable `cwl-grc policy author|revise|list`, `cwl-grc gaps`, `cwl-grc bind`, and the local Uvicorn `cwl-grc serve`.
5. **Kernel package**: `create_app()` for modular composition; `python -m cwl_grc` for standalone local HTTP.
6. **Store**: 3NF SQLite by default, PostgreSQL-ready URL via `CWL_GRC_DATABASE_URL`, versioned schema upgrades, and database triggers that protect audit and finalized policy history.

## Data ownership

| Object | Role |
| --- | --- |
| `policy_document` | Stable policy identity, title, and optimistic current-version counter |
| `policy_version` | Edition finalized exactly once; database triggers reject later update/delete |
| `policy_control_mapping` | Edition → official `control_item`; insert only before finalization and never update/delete |
| `control_framework` | One official catalog edition |
| `control_item` | One official identifier and statement |
| `authorization_purpose` | Declared purpose attached to policy or evidence work; not actor authentication |
| `evidence_record` | Encrypted-at-rest artifact; exact values remain usable in an authorized workflow |
| `control_evidence_binding` | Many-to-many bind of artifact to control |
| `audit_event` | Append-only action record protected at the database boundary; never an audit engagement or finding |
| `audit_program` | Audit period, risk-based rationale, audit authority, creator, and approval (`draft` → `approved`) |
| `audit_engagement` | Engagement under an approved program: scope, period inside the program period, lead auditor, and status `planned` → `fieldwork` → `reporting` → `closed` |
| `engagement_criterion` | Unique engagement → official `control_item` criterion; nullable opaque `internal_control_reference` reserved for Issue #27 |
| `engagement_team_member` | Unique engagement + auditor with `team_role` `lead`, `auditor`, or `supervisor` and a non-empty competence statement |
| `independence_declaration` | Auditor conflict declaration for one engagement; database triggers reject update/delete |
| `audit_procedure` | Procedure for one criterion with population size, selection method, sample size, and optional seed |
| `audit_sample_item` | One selected 1-based population ordinal with optional reference and exception note |
| `audit_evidence_link` | Existing `evidence_record` → exactly one procedure or sample item; to be absorbed by Issue #27 `evidence_usage` |
| `audit_finding` | Finding status, remediation owner, target date, and optimistic current-revision counter |
| `audit_finding_revision` | Append-only finding wording, severity, and rating rationale; database triggers reject update/delete |
| `remediation_action` | Owner, due date, and completion evidence reference |
| `finding_retest` | Independent retest result and evidence reference; database triggers reject update/delete |
| `finding_closure` | One `retest_passed` or time-bounded `risk_accepted` decision per finding; database triggers reject update/delete |
| `schema_migration` | Applied schema-upgrade receipt |

A policy gap is a latest finalized-edition mapping whose control has zero `control_evidence_binding` rows. There is no second evidence-binding table.

Cross-service reads use published HTTP contracts after an authenticated service boundary exists. Peer products do not query these tables.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL triggers reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, and any audit-event update/delete.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

### Audit management

`cwl_grc/audit_management.py` owns the Issue #14 slice (ADR 0017), with request models in `cwl_grc/audit_requests.py` and routes in `cwl_grc/audit_routes.py`. An engagement is created only under a program approved by its audit authority, who is not the program creator, and starts fieldwork only with at least one official criterion, exactly one lead equal to the lead auditor, at least one supervisor, a competence statement for every member, and a no-conflict independence declaration from every member. `seeded_random` sampling stores `sorted(random.Random(seed).sample(range(1, population_size + 1), sample_size))`, so a reviewer can reperform the selection; `full_population` and `judgmental` selections are validated against the population size. Finding revisions append under `audit_finding.current_revision_number`, and a stale `expected_revision` receives `409 Conflict`. A finding closes only after the latest independent retest passed and the lead or a supervisor records closure; `risk_accepted` is a separate status with an expiry no more than 365 days ahead and is a placeholder until Issue #13 governed risk acceptance exists. SQLite and PostgreSQL triggers reject update/delete on `independence_declaration`, `audit_finding_revision`, `finding_retest`, and `finding_closure`, and the upgrade records the `0002_audit_management` receipt. Audit tables reference `evidence_record_id` and never copy plaintext. Every mutation appends an `audit_event`. Role separation compares declared actor identifiers only and is not authenticated until Keyverse identity exists.

## Security posture

The current HTTP surface is an unauthenticated developer preview. `X-Actor-Id` and `X-Purpose` are audit and purpose declarations, not proof of identity. The application binds its command-line server to loopback and always denies non-loopback or proxy-forwarded traffic. There is no unauthenticated remote-preview override.

Production exposure requires Keyverse-backed OIDC signature, issuer, audience, token-type, tenant, actor, and purpose authorization, plus encrypted transport and deployment controls. Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence; authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, the evidence bind contract, and the audit-management routes (`/audit-programs`, `/audit-engagements`, `/audit-procedures`, `/audit-findings`, `/remediation-actions`, `/audit-remediation/overdue`) while replacing the preview boundary with the authenticated Keyverse and tenant-authorization adapter.
