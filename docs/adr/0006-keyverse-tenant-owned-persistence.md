# ADR 0006: Persist Keyverse tenant identifiers on owned GRC records

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0005

## Context

PR #55 authenticates officers with Keyverse access tokens and filters HTTP
reads by verified subject. Records themselves still lacked a tenant column, so
the same actor using another Keyverse `org` could not be isolated at the store.

CWL GRC does not own tenant directories. Keyverse issues the `org` claim.
Owned policy, evidence, and audit rows must carry that identifier so later
PostgreSQL partitions can use `(tenant_identifier, created_by_actor)` rather
than a single hot actor index.

## Decision

1. Add required `tenant_identifier` to `policy_document`, `evidence_record`, and
   `audit_event`.
2. Stamp the verified Keyverse `org` when a verifier is configured. Local
   preview without Keyverse uses `local_preview`.
3. Revision and evidence bind fail closed (404) when the stored tenant does not
   match the caller tenant.
4. Upgrade existing stores with migration `0002_tenant_ownership` and index
   `(tenant_identifier, created_by_actor)` / `(tenant_identifier, collector_actor)`.

## Consequences

Officers in `tenant-acme` cannot read or revise `tenant-other` records even when
the Keyverse subject is the same. Remote deployment still requires encrypted
transport and remaining Keyverse authorization work.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068
