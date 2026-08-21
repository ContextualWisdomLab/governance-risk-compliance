# ADR 0006: Version evidence encryption keys without losing exact evidence

## Status

Accepted for the first key-lifecycle slice stacked after tenant isolation.

## Context

The preview contract used one process-wide Fernet key and stored only ciphertext.
That made an approved key rotation impossible to verify: a record did not identify
which key or algorithm must decrypt it, and a caller could not distinguish a
context mismatch from an accidental key fallback.

GRC must preserve exact authorized evidence, including PII needed for the
workflow. It must not copy KMS/HSM credentials or raw key material into product
tables.

## Decision

1. Inject a provider-neutral EvidenceKeyring with one active key and explicit
   predecessor keys. New writes use only active_key_id; reads name the exact
   stored key and never try another key.
2. Store encryption_key_id, encryption_algorithm_version,
   encryption_context_digest, source_content_digest, and integrity_digest
   beside each evidence ciphertext. Metadata contains no raw key material or
   plaintext.
3. Bind new envelopes to the exact tenant and evidence-record identity. Reject
   unsupported algorithms, unknown or revoked keys, context mismatches, content
   mismatches, and tampered envelope metadata.
4. Keep pre-existing single-key rows explicitly marked as
   fernet-v1-legacy; the migration does not invent a context digest. The
   operator keyring must retain the predecessor under the migration's
   `legacy-v1` key ID until the bounded, repeatable rewrap completes. The
   service appends rewrap_evidence or rewrap_failed audit events.
5. Accept keyring configuration through dependency injection or the process
   environment (CWL_GRC_EVIDENCE_KEYRING_JSON plus
   CWL_GRC_EVIDENCE_ACTIVE_KEY_ID). Raw values remain outside GRC tables.

## Consequences

- Operators can run an overlap window with old and new keys, then remove the old
  key and receive a fail-closed error for any unrewrapped record.
- Rewrap progress is bounded by batch size and the result returns the last
  scanned record ID for complete cursor-based resumption; a failed record is
  not silently rewritten.
- Existing preview evidence remains readable during migration as declared legacy
  data.
- KMS/HSM retrieval, persistent job scheduling, retention/disposition/legal
  hold, encrypted backup, and restore rehearsal remain separate follow-up slices.

## Verification

The regression suite proves active-key writes, old-key overlap reads, revoked-key
failure, context and metadata tamper detection, legacy migration, idempotent
rewrap, audited failure, and 100% statement/branch coverage.

## References

Barker, E. (2020). *Recommendation for key management: Part 1—General* (NIST
Special Publication 800-57 Part 1 Revision 5). National Institute of Standards
and Technology. https://doi.org/10.6028/NIST.SP.800-57pt1r5
