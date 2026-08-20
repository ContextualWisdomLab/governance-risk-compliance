# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. The current stack owns versioned policies, the official control catalog, exact-value evidence artifacts, control–evidence bindings, uncovered policy/control queries, verified Keyverse principals, and tenant-scoped authorization. The network surface remains a loopback-only product preview until the remaining production-deployment gates are implemented.

```mermaid
flowchart LR
    officer[Compliance officer] --> home[Local officer home /]
    officer --> api[Policy, control, and evidence API]
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
    kernel --> binding[(tenant-owned evidence bindings)]
    kernel --> audit[(tenant-owned audit events)]
    consumers[Orgmetra / AIS / Billing / naruon / EA / SDP] -. future authenticated contracts .-> api
```

## Runtime layers

1. **Local officer home**: buyer-oriented HTML that authors a policy, lists policy gaps, and attaches the next evidence under the fixed `local_development` tenant.
2. **HTTP API**: policy author/revise/list, policy-gap query, catalog list, uncovered query, evidence create, evidence bind, and dependency-separated `/healthz`, `/readyz`, and `/startupz` probes.
3. **Keyverse security adapter**: optional closed-profile JWT verification plus bounded OIDC Discovery/JWKS loading. When configured, protected policy and evidence routes derive actor and tenant from the signed principal and enforce action-specific scopes.
4. **Preview network boundary**: always rejects proxy-forwarded and non-loopback traffic. Keyverse authentication inside the process does not enable customer or Internet exposure by itself.
5. **CLI tools**: executable `cwl-grc policy author|revise|list`, `cwl-grc gaps`, `cwl-grc bind`, and the local Uvicorn `cwl-grc serve`.
6. **Kernel package**: `create_app()` for modular composition; `python -m cwl_grc` for standalone local HTTP.
7. **Store**: 3NF SQLite by default, PostgreSQL-ready URL via `CWL_GRC_DATABASE_URL`, versioned schema upgrades, and database guards that protect tenant relationships, audit history, and finalized policy history.
8. **Operations boundary**: bounded PostgreSQL connection setup, startup admission checks, drain state, W3C request correlation, redaction-safe structured request logs, and low-cardinality OpenTelemetry request/session-transaction traces and metrics. Collector configuration, pool instrumentation, dashboards, SLOs, and alert rules remain platform integration work.

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
| `control_evidence_binding` | Tenant-owned bind of an evidence artifact to a shared official control |
| `audit_event` | Tenant-owned append-only action record protected at the database boundary |
| `schema_migration` | Applied schema-upgrade receipt |

Every tenant-owned row has a non-null `tenant_id`. In Keyverse mode it comes from the verified `org` claim. The `local_development` value is reserved for the loopback-only compatibility profile and migration of pre-tenant preview data.

A policy gap is a latest finalized-edition mapping whose control has zero same-tenant `control_evidence_binding` rows. There is no second evidence-binding table. Cross-service reads use published HTTP contracts after a production-authenticated service boundary exists; peer products never query these tables directly.

## Tenant relationship integrity

Application queries filter policy, mapping, evidence, binding, and gap records by the verified tenant. Guessed cross-tenant mutation identifiers return `404 Not Found` so the caller cannot distinguish another tenant's object from a nonexistent object.

Application filtering is not the sole control. New schemas pair tenant and parent identifiers through named composite foreign-key constraints:

- `policy_version(tenant_id, policy_document_id)` → `policy_document(tenant_id, policy_document_id)`;
- `policy_control_mapping(tenant_id, policy_version_id)` → `policy_version(tenant_id, policy_version_id)`;
- `control_evidence_binding(tenant_id, evidence_record_id)` → `evidence_record(tenant_id, evidence_record_id)`.

Existing SQLite and PostgreSQL stores receive idempotent tenant-parent guards at startup, because adding composite constraints to an already-created SQLite table would otherwise require a destructive table rebuild. The guards fail closed on mismatched parent inserts or updates.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its same-tenant official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL guards reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, and any audit-event update/delete.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a tenant-bound conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

## Security posture

The application has two loopback-only execution profiles:

- **Local development** uses the fixed `local_development` tenant and explicit actor/purpose declarations for the local officer UI and CLI. Those declarations are not authentication.
- **Keyverse-enabled composition** requires verified bearer identity and action scope for protected policy and evidence routes. Caller-supplied `X-Actor-Id` never overrides the signed principal. Policy and policy-gap reads require `grc.policy.read`; mutations require their corresponding policy or evidence write scope.

Both profiles remain behind the same loopback-only boundary, which rejects non-loopback and proxy-forwarded traffic. Remote exposure still requires production issuer configuration, complete purpose/resource authorization, deployment identity, encrypted transport, operational controls, and acceptance evidence.

Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence. Authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, and the evidence bind contract while replacing the loopback preview boundary with the completed Keyverse authorization, deployment, and operator-control profile. The standalone and extracted service must enforce the same tenant-parent database invariants.
