# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. This slice owns versioned policies, the official control catalog, evidence artifacts, control–evidence bindings, and uncovered policy/control queries. GRC Analytics is a separate read-only Supporting Bounded Context: it consumes governed projections of GRC truth without becoming a second source of truth or a model-provider boundary.

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
    keyverse[Keyverse OIDC / tenant authorization] -. required before remote deployment .-> preview
    consumers[Orgmetra / Keyverse / AIS / Billing / naruon / EA / SDP] -. future authenticated contracts .-> api
    question[Authorized Ask GRC question] --> orchestrator[contextual-orchestrator ACL]
    orchestrator --> intent[cwl_grc.analytics semantic intent]
    intent --> planner[deterministic read-only query plan]
    planner -. future allowlisted executor .-> projections[(GRC analytics read projections)]
    policy -. governed projection .-> projections
    catalog -. governed projection .-> projections
    evidence -. governed projection .-> projections
    audit -. governed projection .-> projections
    projections -. bounded facts + provenance .-> orchestrator
```

## Runtime layers

1. **Officer home**: buyer-oriented HTML that authors a policy, lists policy gaps, and attaches the next evidence in a local preview.
2. **HTTP API**: policy author/revise/list, policy-gap query, catalog list, uncovered query, evidence create, evidence bind, `/healthz`.
3. **Preview network boundary**: always rejects proxy-forwarded and non-loopback traffic; no runtime override exists before Keyverse authentication.
4. **CLI tools**: executable `cwl-grc policy author|revise|list`, `cwl-grc gaps`, `cwl-grc bind`, and the local Uvicorn `cwl-grc serve`.
5. **Kernel package**: `create_app()` for modular composition; `python -m cwl_grc` for standalone local HTTP.
6. **Store**: 3NF SQLite by default, PostgreSQL-ready URL via `CWL_GRC_DATABASE_URL`, versioned schema upgrades, and database triggers that protect audit and finalized policy history.
7. **Analytics Supporting Context**: `cwl_grc.analytics.domain` owns versioned semantic intent/query-plan types and `cwl_grc.analytics.application` owns deterministic planning. No database or LLM provider adapter is part of this increment.

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
| `audit_event` | Append-only action record protected at the database boundary |
| `schema_migration` | Applied schema-upgrade receipt |
| `cwl.grc.analytics.intent.v1` | Untrusted structured analysis intent; contains semantic fields and question hash, never SQL |
| `cwl.grc.analytics.query-plan.v1` | Authorized, bounded, read-only plan coordinate over a versioned analytics projection |

A policy gap is a latest finalized-edition mapping whose control has zero `control_evidence_binding` rows. There is no second evidence-binding table.

Cross-service reads use published HTTP contracts after an authenticated service boundary exists. Peer products do not query these tables.

## GRC Analytics context map

The authoritative Policy, External Requirement/Catalog, Internal Control, Evidence, Risk, Audit, and Remediation contexts remain upstream of Analytics. Analytics receives only purpose-authorized projections or read-replica/materialized-view representations with explicit provenance and freshness. It does not copy those product tables into a new ledger.

Keyverse is upstream identity/tenant/workspace/purpose authority. A verified authorization decision is supplied to Analytics planning; caller-declared identity headers are not accepted as identity.

`contextual-orchestrator` is the Anti-Corruption Layer for natural-language interpretation and grounded synthesis. GRC does not directly own OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Bytez, or other model-provider clients/credentials for interactive analytics. The orchestration layer may propose a structured intent, but GRC validates semantic fields, bounds, time axes, and field policy before any read execution.

The current contract admits framework/edition, obligation/jurisdiction, policy/status, internal control/type/frequency/owner, implementation/system scope, evidence source/period/freshness/quality, control test/result/effectiveness, risk, audit, remediation, tenant/workspace, effective/business time, and system-recorded time semantics. Availability is distinct from admission: an authorized field that is not backed by the current read projection returns `insufficient_evidence`.

No raw SQL field exists in the version-one query plan. A future executor must map the semantic plan to allowlisted read-only views with mandatory tenant/workspace/purpose predicates, bind parameters, AST/parser validation where SQL is generated, bounded joins/result size/time/cost/concurrency, cancellation, and a read-only database credential. DML, DDL, arbitrary schemas, system catalogs, secret/config tables, multi-statements, and unsafe functions remain outside the contract.

Typed fail-closed outcomes are `not_authorized`, `insufficient_evidence`, and `unsupported_analysis`. A model must not replace one of these outcomes with a guessed answer or widen hidden conversational scope.

## DDD fitness

New GRC Analytics code uses explicit `analytics/domain` and `analytics/application` ownership instead of adding more responsibilities to flat `utils`, `helpers`, `common`, `services`, `lib`, `shared`, `core`, `models`, `misc`, or `legacy` buckets. Architectural tests reject provider/database dependencies in the Analytics bounded context and reject dependencies from its domain layer into the existing flat application/kernel modules.

The existing flat kernel remains legacy structure to migrate only through coherent owner-bound moves with compatibility mapping and regression evidence. The Analytics slice does not perform cosmetic directory churn or split a transactionally cohesive modular monolith merely to create services.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL triggers reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, and any audit-event update/delete.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

Analytics plans are immutable values. A plan is bound to verified principal/tenant/workspace/purpose coordinates, an authorization decision reference, a SHA-256 question hash, a semantic schema version, and bounded dimensions/measures/filters/time range. Later execution and query receipts must preserve those coordinates so a follow-up cannot silently expand scope.

## Security posture

The current HTTP surface is an unauthenticated developer preview. `X-Actor-Id` and `X-Purpose` are audit and purpose declarations, not proof of identity. The application binds its command-line server to loopback and always denies non-loopback or proxy-forwarded traffic. There is no unauthenticated remote-preview override.

Production exposure requires Keyverse-backed OIDC signature, issuer, audience, token-type, tenant, actor, and purpose authorization, plus encrypted transport and deployment controls. Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence; authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

GRC Analytics does not authorize or execute risk acceptance, control approval, policy publication, audit-finding closure, evidence disposition, exception approval, certification/compliance decisions, or tenant/security changes. Its outputs are analysis/explanation/proposal artifacts only. Deterministic GRC domain commands remain the only route to authoritative state transition.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, and the evidence bind contract while replacing the preview boundary with the authenticated Keyverse and tenant-authorization adapter.

If the Analytics context is later deployed separately, extraction must preserve its versioned semantic/query/result contracts and read-only projection boundary. It must not move authoritative GRC tables or provider credentials into the analytics process merely to simplify deployment.
