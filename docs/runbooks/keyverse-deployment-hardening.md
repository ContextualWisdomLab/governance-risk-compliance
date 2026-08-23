# Keyverse deployment-hardening runbook

This runbook is for operators of the **local developer preview**. It does not
make CWL GRC a production deployment. Do not route non-loopback traffic until
Keyverse-backed identity, tenant authorization, encrypted transport, and
independent admission exist.

Next action: keep the process on `127.0.0.1`, confirm the Keyverse JWKS and
issuer, then author the next official-control policy or attach the next
evidence.

## Schema migration `0003_audit_attribution`

Apply:

1. Stop mutating officer traffic (see emergency read-only).
2. Start the process against the existing store. `create_session_factory`
   applies `0003_audit_attribution` once and writes a `schema_migration`
   receipt.
3. Confirm `audit_event` has `issuer_identifier`, `client_identifier`,
   `correlation_reference`, and `decision_outcome`.
4. Confirm a pre-migration row shows `local_preview` / `legacy_unattributed` /
   `allow`. New Keyverse-authenticated rows must show the real issuer and
   client, never a compact JWT.

Rollback:

- SQLite cannot drop these columns in place. Restore the pre-migration
  database file from backup.
- Do not rewrite append-only `audit_event` history. If attribution was applied
  incorrectly, restore the backup rather than UPDATE/DELETE audit rows.

## Key rotation

Keyverse remains the issuer. GRC verifies overlapping reviewed public JWKs
(old and new `kid` values) and never fetches private keys.

1. Load the reviewed JWKS that contains both current and next signing keys.
2. Confirm a newly issued officer token (`typ=at+jwt`, RS256) authors a CSAP
   policy and writes an audit row with the same issuer and client.
3. After Keyverse stops signing with the old key, load a JWKS that omits it.
4. If the JWKS contains unknown, duplicate, private, or non-RS256 keys, the
   loader fails closed. Do not start the process on that snapshot.

## Issuer unavailable

The HTTP adapter consumes an injected verifier. It does not discover Keyverse
at request time.

- If OIDC metadata or JWKS cannot be loaded, do not inject a verifier and do
  not expose the process beyond loopback.
- Local preview without a verifier still accepts declared `X-Actor-Id` headers.
  That mode is not authentication and is not a customer deployment.
- Do not cache an untrusted issuer. Do not disable issuer checks.

## Clock skew

Configured skew must be an integer between 0 and 300 seconds. Expired tokens,
future `iat`, and inactive `nbf` fail closed. If officers see unexpected 401s
after a time change, correct the host clock; do not raise skew above 300
seconds.

## Emergency read-only

1. Leave the process bound to `127.0.0.1`. Remote and forwarded requests
   already return 503.
2. Do not introduce an unauthenticated remote-preview override. That hatch was
   removed.
3. Stop the process if write access must cease. This slice has no production
   drain flag.
4. Catalog `GET /controls` and `GET /healthz` stay unauthenticated because they
   expose published control identifiers and liveness, not tenant records.

## What remains before production

Encrypted transport, Keyverse-backed admission of customer traffic, and
independent review of the remaining Issue #4 authorization work. Until those
exist, treat every deployment of this kernel as a local developer preview.
