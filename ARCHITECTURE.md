# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. The current stack owns versioned policies, the official control catalog, exact-value evidence artifacts, control–evidence bindings, uncovered policy/control queries, verified Keyverse principals, and tenant-scoped authorization. The network surface remains a loopback-only product preview until the remaining production-deployment gates are implemented.

```mermaid
flowchart LR
    officer[Compliance officer] --> home[Local officer home /]
    officer --> api[Policy, obligation, control, evidence, and workspace API]
    officer --> cli[cwl-grc CLI]
    home --> preview[Loopback-only preview boundary]
    api --> preview
    keyverse[Keyverse OIDC issuer] --> loader[Bounded Discovery / JWKS loader]
    loader --> verifier[Closed access-token verifier]
    verifier --> authz[Verified principal / tenant / scope]
    authz --> preview
    preview --> kernel[cwl_grc kernel]
    cli --> kernel
    probe[/healthz] --> preview
    ready_probe[/readyz] --> preview
    startup_probe[/startupz] --> preview
    preview --> telemetry[Correlated JSON logs + OpenTelemetry]
    kernel --> policy[(tenant-owned policy records)]
    kernel --> catalog[(shared control catalog)]
    kernel --> evidence[(tenant-owned evidence records)]
    kernel --> requests[(tenant-owned evidence requests)]
    kernel --> binding[(legacy evidence bindings)]
    kernel --> controls[(internal control definitions, tests, and status projection)]
    kernel --> obligations[(sources, obligations, applicability, and change impact)]
    kernel --> audit[(tenant-owned audit events)]
    consumers[Orgmetra / AIS / Billing / naruon / EA / SDP] -. future authenticated contracts .-> api
```

## Runtime layers

1. **Local officer home**: buyer-oriented HTML that authors a policy, lists explicit control statuses and policy gaps, and stores evidence for a future control test under the fixed `local_development` tenant. Evidence-request workflow state is exposed through the JSON surface and remains outside this static form until the PR34 buyer UI authority adopts it.
2. **HTTP API**: policy author/revise/list, obligation source/revision/register/decision/link/change/impact workflows, tenant-scoped `/compliance-workspace` posture, evidence-request collection/review, policy-gap query, catalog list, uncovered query, evidence create, evidence bind, and dependency-separated `/healthz`, `/readyz`, and `/startupz` probes.
3. **Keyverse security adapter**: optional closed-profile JWT verification plus bounded OIDC Discovery/JWKS loading. When configured, protected policy and evidence routes derive actor and tenant from the signed principal and enforce action-specific scopes.
4. **Preview network boundary**: always rejects proxy-forwarded and non-loopback traffic. Keyverse authentication inside the process does not enable customer or Internet exposure by itself.
5. **CLI tools**: executable `cwl-grc policy author|revise|list`, `cwl-grc gaps`, `cwl-grc bind`, and the local Uvicorn `cwl-grc serve`.
6. **Kernel package**: `create_app()` for modular composition; `python -m cwl_grc` for standalone local HTTP.
7. **Store**: 3NF SQLite by default, PostgreSQL-ready URL via `CWL_GRC_DATABASE_URL`, versioned schema upgrades, and database guards that protect tenant relationships, audit history, finalized policy history, and internal-control test history.
8. **Operations boundary**: bounded PostgreSQL connection setup, startup admission checks, drain state, W3C request correlation, redaction-safe structured request logs, and low-cardinality OpenTelemetry request/session-transaction traces plus request/session-transaction/pool/recovery-event metrics. Collector configuration, dashboards, SLOs, and alert rules remain platform integration work.

## Data ownership

| Object | Ownership and role |
| --- | --- |
| `policy_document` | Tenant-owned stable policy identity, title, and optimistic current-version counter |
| `policy_version` | Tenant-owned edition finalized exactly once; paired to its tenant-owned policy parent |
| `policy_control_mapping` | Tenant-owned edition → shared official `control_item`; insert only before finalization and never update/delete |
| `control_framework` | Shared official catalog edition; not customer-owned |
| `control_item` | Shared official identifier and statement; not customer-owned |
| `authorization_purpose` | Shared declared-purpose vocabulary; not actor authentication |
| `evidence_record` | Tenant-owned encrypted-at-rest artifact; exact values remain usable in an authorized workflow |
| `evidence_request` | Tenant-owned scope/period/submission/review workflow metadata linked to one same-tenant evidence artifact |
| `control_evidence_binding` | Tenant-owned legacy compatibility bind of an evidence artifact to a shared official control; never an effectiveness conclusion |
| `control_objective` | Tenant-owned objective grouping reusable internal controls |
| `internal_control_definition` | Tenant-owned reusable control definition |
| `control_definition_version` | Immutable version of the control statement and test expectations |
| `control_implementation` | Tenant-scoped implementation and scope reference |
| `control_owner_assignment` | Temporal accountable/operator/reviewer assignment |
| `control_requirement_mapping` | Reviewed many-to-many relation to an official catalog requirement |
| `control_test_plan` | Design or operating test method and cadence |
| `control_test_execution` | Immutable historical test period and sample |
| `control_test_result` | Immutable design/operating conclusion |
| `control_exception` | Time-bounded approved exception |
| `control_deficiency` | Open or resolved failure requiring remediation |
| `evidence_usage` | Purpose-approved evidence use for one implementation and completed test; legacy rows are `unassessed` |
| `audit_event` | Tenant-owned append-only action record protected at the database boundary |
| `jurisdiction_record` | Tenant-scoped jurisdiction reference, not a copied legal body |
| `regulatory_source` | Authoritative legal, contractual, voluntary, or internal source pointer |
| `source_revision` | Immutable source edition, date, digest, and lawful artifact reference |
| `compliance_obligation` | Immutable source-backed obligation for one precise scope and period |
| `obligation_requirement` | Reviewed obligation link to a finalized policy or internal control |
| `applicability_rule` | Reviewable rule proposal for one obligation |
| `applicability_decision` | Immutable evidenced applicability conclusion and next review |
| `legal_interpretation` | Attributed interpretation reference, not legal advice |
| `compliance_commitment` | Separate contractual or voluntary commitment |
| `obligation_owner_assignment` | Temporal obligation owner reference |
| `regulatory_change` | Immutable source change intake and diff reference |
| `change_impact_assessment` | Immutable owner, due date, implementation, and re-approval assessment |
| `schema_migration` | Applied schema-upgrade receipt |

Every tenant-owned row has a non-null `tenant_id`. In Keyverse mode it comes from the verified `org` claim. The `local_development` value is reserved for the loopback-only compatibility profile and migration of pre-tenant preview data.

A policy gap is a latest finalized-edition mapping whose external control projects to a status other than `operating_effective` or authorized `not_applicable`. Direct `control_evidence_binding` rows remain compatibility data and project to `unassessed`; `evidence_usage` records a purpose-approved use without replacing the legacy binding model. Cross-service reads use published HTTP contracts after a production-authenticated service boundary exists; peer products never query these tables directly.

## Tenant relationship integrity

Application queries filter policy, mapping, evidence, binding, and gap records by the verified tenant. Guessed cross-tenant mutation identifiers return `404 Not Found` so the caller cannot distinguish another tenant's object from a nonexistent object.

Application filtering is not the sole control. New schemas pair tenant and parent identifiers through named composite foreign-key constraints:

- `policy_version(tenant_id, policy_document_id)` → `policy_document(tenant_id, policy_document_id)`;
- `policy_control_mapping(tenant_id, policy_version_id)` → `policy_version(tenant_id, policy_version_id)`;
- `control_evidence_binding(tenant_id, evidence_record_id)` → `evidence_record(tenant_id, evidence_record_id)`.
- `evidence_request(tenant_id, evidence_record_id)` → `evidence_record(tenant_id, evidence_record_id)` when a request has a submission.
- `source_revision(tenant_id, regulatory_source_id)` → `regulatory_source(tenant_id, regulatory_source_id)`;
- `compliance_obligation(tenant_id, source_revision_id)` → `source_revision(tenant_id, source_revision_id)`;
- applicability, owner, requirement, change, and impact rows pair tenant keys with their parent identifiers.
- `internal_control_definition(tenant_id, objective_id)` → `control_objective(tenant_id, objective_id)`;
- `control_definition_version(tenant_id, internal_control_definition_id)` → `internal_control_definition(tenant_id, internal_control_definition_id)`;
- `control_implementation(tenant_id, internal_control_definition_id)` → `internal_control_definition(tenant_id, internal_control_definition_id)`;
- test plans, executions, results, deficiencies, exceptions, and evidence usage pair every tenant key with their parent identifier.

Existing SQLite and PostgreSQL stores receive idempotent tenant-parent guards at startup, and SQLite foreign-key enforcement is enabled on every product connection. The guards fail closed on mismatched parent inserts or updates without destructively rewriting evidence.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its same-tenant official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL guards reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, audit-event update/delete, and mutation of published internal-control or obligation history, reviewed mappings, test executions/results, or evidence usage.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a tenant-bound conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

## Security posture

The application has two loopback-only execution profiles:

- **Local development** uses the fixed `local_development` tenant and explicit actor/purpose declarations for the local officer UI and CLI. Those declarations are not authentication.
- **Keyverse-enabled composition** requires verified bearer identity and action scope for protected policy, evidence, coverage, and officer-console routes. Caller-supplied `X-Actor-Id` never overrides the signed principal. Policy, policy-gap, coverage-gap, and officer-console reads require `grc.policy.read`; mutations require their corresponding policy or evidence write scope.

Both profiles remain behind the same loopback-only boundary, which rejects non-loopback and proxy-forwarded traffic. Remote exposure still requires production issuer configuration, complete purpose/resource authorization for obligation routes as well as policy/evidence routes, deployment identity, encrypted transport, operational controls, and acceptance evidence.

Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence. Authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, `/compliance-workspace`, and the evidence bind contract while replacing the loopback preview boundary with the completed Keyverse authorization, deployment, and operator-control profile. The standalone and extracted service must enforce the same tenant-parent database invariants.
