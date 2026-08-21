# ADR 0014: Govern a tenant-scoped evidence request workflow

## Status

Proposed; requires independent review and protected merge at the exact source
head. This is a local-preview workflow contract, not a production identity or
auditor data-room deployment.

## Context

Evidence artifacts already have encrypted storage, retention metadata, legal
holds, same-tenant control bindings, and append-only audit events. An officer
still needs to request a defined period and scope from a named contributor,
receive an existing artifact, and record an independent acceptance or
rejection without copying the artifact payload into another table.

## Decision

1. Add `evidence_request` as one tenant-owned state row with the request title,
   scope, period, metadata-only required field names, contributor reference,
   due date, reuse policy, submission identity, review identity, and outcome.
2. Permit only `requested → submitted → accepted|rejected` transitions. The
   contributor must be the authenticated actor named by the request, and the
   reviewer must differ from the contributor. A rejected request is terminal;
   a corrected submission creates a new request so its audit history remains
   unambiguous.
3. Link an existing same-tenant `evidence_record` through a composite foreign
   key. The request routes never decrypt or return its payload; authorized
   evidence reads remain the existing purpose-specific workflow.
4. Reuse the existing `compliance_governance` purpose and `grc.compliance.*`
   scopes for request metadata and review. Local-preview actor headers remain
   declarations, never authentication; Keyverse mode derives actor and tenant
   from the signed bearer token.
5. Project request rows and state counts into `/compliance-workspace`, while
   keeping risks, auditor data rooms, controlled exports, and automated
   retention disposition outside this slice.

## Consequences

The buyer can track a bounded evidence collection and review loop with exact
scope, period, due date, reuse policy, outcome, and audit history. The first
slice intentionally supports one submission per request; resubmission history
is represented by a new request rather than a second submission table. A
future production data-room or export contract must add purpose-specific field
selection, authorization, reproducibility, retention, and independent
deployment evidence.

## Verification

`tests/test_evidence_requests.py` covers malformed request metadata,
same-tenant evidence binding, contributor/reviewer separation, accepted and
rejected outcomes, audit history, payload non-disclosure, and invalid database
state transitions. SQLite and PostgreSQL integrity DDL are installed through
the existing schema-migration and guard path.
