# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. This slice owns versioned policies, the official control catalog, evidence artifacts, control–evidence bindings, uncovered policy/control queries, and the explicit database-schema lifecycle required to run those objects safely.

```mermaid
flowchart LR
    officer[Compliance officer] --> home[Officer home /]
    officer --> api[Policy, control, and evidence API]
    officer --> cli[cwl-grc officer CLI]
    operator[Database operator] --> migrate[cwl-grc database migrate]
    operator --> check[cwl-grc database check]
    home --> preview[Local-only developer preview boundary]
    api --> preview
    preview --> kernel[cwl_grc kernel]
    cli --> kernel
    probe[/healthz] --> preview
    migrate --> lock[Single PostgreSQL advisory migration owner]
    lock --> schema[(Versioned schema and reference bootstrap)]
    check --> compatibility[DDL-free compatibility check]
    compatibility --> schema
    kernel --> runtime[Runtime session factory]
    runtime --> compatibility
    runtime --> policy[(policy_document / policy_version / policy_control_mapping)]
    runtime --> catalog[(control_framework / control_item)]
    runtime --> evidence[(evidence_record)]
    runtime --> binding[(control_evidence_binding)]
    runtime --> audit[(audit_event)]
    keyverse[Keyverse OIDC / tenant authorization] -. required before remote deployment .-> preview
    consumers[Orgmetra / Keyverse / AIS / Billing / naruon / EA / SDP] -. future authenticated contracts .-> api
```

## Runtime layers

1. **Officer home**: buyer-oriented HTML that authors a policy, lists policy gaps, and attaches the next evidence in a local preview.
2. **HTTP API**: policy author/revise/list, policy-gap query, catalog list, uncovered query, evidence create, evidence bind, and `/healthz`.
3. **Preview network boundary**: always rejects proxy-forwarded and non-loopback traffic; no runtime override exists before Keyverse authentication.
4. **Officer CLI**: executable `cwl-grc policy author|revise|list`, `cwl-grc gaps`, `cwl-grc bind`, and local Uvicorn `cwl-grc serve`.
5. **Database operator CLI**: `cwl-grc database migrate` is the only schema-owning command; `cwl-grc database check` verifies the exact schema and reference vocabulary without DDL.
6. **Kernel package**: `create_app()` for modular composition; `python -m cwl_grc` for standalone local HTTP.
7. **Store**: 3NF SQLite for the local profile and PostgreSQL 18 for the supported production database profile. PostgreSQL acceptance is exercised on 18.4 with `psycopg[binary]` 3.3.4.

## Schema ownership and compatibility

Application replicas do not own production DDL. The deployment sequence is:

1. run one `cwl-grc database migrate --database-url …` owner;
2. acquire the fixed PostgreSQL transaction advisory lock before any schema mutation;
3. create the current tables, apply ordered migration receipts, install integrity guards, and seed the exact shared framework/control/purpose vocabulary;
4. run `cwl-grc database check --database-url …`;
5. start replicas with `CWL_GRC_SCHEMA_MODE=runtime`.

Runtime mode is read-only with respect to schema and reference vocabulary. It fails before serving when the database is uninitialized, missing required tables or migration receipts, contains an unknown future receipt, or has an incomplete/incompatible shared catalog or purpose set. The local `development` mode retains automatic preparation only for the loopback developer preview.

The initial released receipt is `0001_policy_integrity`. Future changes must add immutable ordered receipts and prove clean installation plus every supported upgrade path. Downgrade is not supported or claimed. Expand/backfill/contract operations and emergency handling are defined in `docs/operations/postgresql-schema-lifecycle.md`.

## PostgreSQL connection policy

The only supported SQLAlchemy PostgreSQL dialect is `postgresql+psycopg`.

- Remote connections use `sslmode=verify-full`.
- TLS may be disabled only through an explicit loopback CI settings object.
- Connection, statement, lock, idle-transaction, pool-acquisition, overflow, and recycle behavior is finite.
- `lock_timeout` is strictly lower than `statement_timeout` so lock contention fails with the more specific boundary first.
- Connections use pool pre-ping and `READ COMMITTED` isolation.
- A concurrent migration owner receives a bounded advisory-lock failure before DDL.

The digest-pinned PostgreSQL 18.4 workflow verifies clean install, DDL-free runtime startup, trigger parity, migration-lock contention, session timeout policy, reference compatibility, and process restart on the exact pull-request head.

## Data ownership

| Object | Role |
| --- | --- |
| `policy_document` | Stable policy identity, title, and optimistic current-version counter |
| `policy_version` | Edition finalized exactly once; database triggers reject later update/delete |
| `policy_control_mapping` | Edition → official `control_item`; insert only before finalization and never update/delete |
| `control_framework` | One official catalog edition; migration-owned shared reference data |
| `control_item` | One official identifier and statement; migration-owned shared reference data |
| `authorization_purpose` | Declared purpose vocabulary; migration-owned and not actor authentication |
| `evidence_record` | Encrypted-at-rest artifact; exact values remain usable in an authorized workflow |
| `control_evidence_binding` | Many-to-many bind of artifact to control |
| `audit_event` | Append-only action record protected at the database boundary |
| `schema_migration` | Append-only applied schema-upgrade receipt and binary-compatibility boundary |

A policy gap is a latest finalized-edition mapping whose control has zero `control_evidence_binding` rows. There is no second evidence-binding table.

Cross-service reads use published HTTP contracts after an authenticated service boundary exists. Peer products do not query these tables.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL triggers reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, and any audit-event update/delete.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

Schema concurrency is separate from policy concurrency. PostgreSQL migration ownership uses a transaction-scoped advisory key, while application runtime performs compatibility checks only and never races schema or reference-data writes.

## Security posture

The current HTTP surface is an unauthenticated developer preview. `X-Actor-Id` and `X-Purpose` are audit and purpose declarations, not proof of identity. The application binds its command-line server to loopback and always denies non-loopback or proxy-forwarded traffic. There is no unauthenticated remote-preview override.

Production exposure requires Keyverse-backed OIDC signature, issuer, audience, token-type, tenant, actor, and purpose authorization, plus encrypted transport and deployment controls. Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence; authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

Database TLS verification and migration ownership do not make the product production-ready by themselves. Backup/restore and evidence-key recovery, release artifacts, observability/readiness, API hardening, risk workflows, audit-program workflows, and remote tenant authorization remain separate readiness gates.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, the evidence bind contract, and the explicit migrate/check split while replacing the preview boundary with the authenticated Keyverse and tenant-authorization adapter.
