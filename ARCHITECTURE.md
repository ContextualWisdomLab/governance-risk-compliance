# ARCHITECTURE.md

## Architecture thesis

CWL GRC is a modular microservice that must run alone or be imported as `cwl_grc`. This slice owns versioned policies, the official control catalog, evidence artifacts, control–evidence bindings, and uncovered policy/control queries.

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
```

## Runtime layers

1. **Officer home**: officer-oriented HTML that authors a policy, lists policy gaps, and attaches the next evidence in a local preview.
2. **HTTP API**: policy author/revise/list, policy-gap query, catalog list, uncovered query, local-only `/workspace/posture` projection, evidence create, evidence bind, `/healthz`.
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
| `audit_event` | Append-only action record protected at the database boundary |
| `schema_migration` | Applied schema-upgrade receipt |

A policy gap is a latest finalized-edition mapping whose control has zero `control_evidence_binding` rows. There is no second evidence-binding table.

Cross-service reads use published HTTP contracts after an authenticated service boundary exists. Peer products do not query these tables.

## Integrity and concurrency

Policy creation writes an unfinalized `policy_version`, writes its official-control mappings, and then performs the only permitted transition to `is_finalized=true`. SQLite and PostgreSQL triggers reject later policy-version mutation or deletion, mapping insertion after finalization, mapping update/delete, and any audit-event update/delete.

`policy_document.current_version_number` is the optimistic concurrency token. A revision advances it with a conditional SQL update. A stale writer receives `409 Conflict` and must reload the current edition; the service never guesses a replacement version number.

## Security posture

The current HTTP surface is an unauthenticated developer preview. `X-Actor-Id` and `X-Purpose` are audit and purpose declarations, not proof of identity. The application binds its command-line server to loopback and always denies non-loopback or proxy-forwarded traffic. There is no unauthenticated remote-preview override.

Production exposure requires Keyverse-backed OIDC signature, issuer, audience, token-type, tenant, actor, and purpose authorization, plus encrypted transport and deployment controls. Evidence payloads remain encrypted at rest. Every persistent store requires explicit Fernet key material; ephemeral keys exist only for explicitly selected in-memory tests. The product does not destructively mask operational evidence; authenticated views and exports must select only the fields required for the approved purpose and omit unrelated fields. SAST remains a CWL Security lane. OPA/Rego is not part of this kernel.

## Officer-workspace projection boundary

Issue #30 introduces a bounded design authority at `apps/grc-workspace/`, paired with Figma file `ta1jjWSjmADz2BFxka9UPs` and repository Storybook. The fixture is intentionally outside the authoritative domain kernel: it demonstrates how an officer sees `unknown`, `not assessed`, `stale`, `blocked`, and `access denied`, how a posture claim leads to the next action, and how projected summaries expose exact-value tables. The local-only `/workspace/posture` route provides the backend projection with the same fail-closed boundary; it does not claim tenant authorization or control effectiveness.

The workspace must consume authenticated GRC contracts when those dependencies integrate; it must not query persistence tables directly or invent a parallel source of truth. Figma/Storybook states are design evidence only. Authentication, tenant/purpose authorization, evidence requests, exports, and data-room grants remain owned by their corresponding GRC/Keyverse contracts. ADR 0012 records the token, accessibility, i18n, component, and ownership decision.

## Service extraction

The kernel is already a separately importable package. Extracting the process onto its own host must preserve `/healthz`, `/policy-documents`, `/policy-gaps`, `/controls`, `/controls/uncovered`, `/workspace/posture`, and the evidence bind contract while replacing the preview boundary with the authenticated Keyverse and tenant-authorization adapter.
