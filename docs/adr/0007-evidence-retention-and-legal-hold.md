# ADR 0007: Preserve evidence while recording retention and legal holds

## Status

Accepted for the retention metadata and legal-hold slice.

## Context

Evidence must remain exact and usable for an authorized workflow. A retention
decision cannot be represented safely by masking or deleting the artifact, and a
legal hold must override any later disposition workflow. The preview had no
retention state or purpose-specific operation for hold changes.

## Decision

1. Store retention_class, retention_started_at, disposition_due_at,
   legal_hold_active, legal_hold_reason, legal_hold_authority, and
   disposition_outcome on each evidence record.
2. Backfill legacy retention_started_at from collected_at and use a standard
   retention class; do not invent a disposition date or hold authority.
3. Require the new evidence_retention purpose and `grc.evidence.retention`
   scope for HTTP legal-hold placement and release when Keyverse verification is
   enabled. Local preview mode keeps the same purpose contract through its
   declared actor headers.
4. Keep legal-hold changes tenant-filtered and audited. Releasing a hold leaves
   the recorded reason and authority available for review.
5. Do not implement destructive disposition, KMS/HSM retrieval, backup/restore,
   or remote exposure in this slice. Those need an approved operating contract.

## Consequences

- An officer can record a retention class and due date without changing the
  encrypted payload.
- A held record remains identifiable as held, and a release is explicit and
  auditable before a future disposition worker may act.
- Legacy stores receive deterministic metadata during migration.
- Actual disposition, retention schedules, recovery objectives, and provider
  integration remain open gaps rather than unverified production claims.

## Verification

The regression suite covers invalid dates and hold fields, same-tenant legal-hold
placement and release, idempotent release, legacy migration columns, protected
HTTP serialization, and 100% statement/branch coverage. A separate PostgreSQL
probe verifies all seven retention columns and the hold state transition.
