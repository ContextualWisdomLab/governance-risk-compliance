# ADR 0003: Version one policy API is strict, replay-safe, and paginated

## Status

Accepted for the first buyer-facing API contract.

## Context

The original policy routes accept arbitrary dictionaries, return unbounded
collections, and expose endpoint-specific error shapes. A compliance officer
integrating policy authoring with a control/evidence workflow needs a stable
contract: unknown fields must fail before a write, retries must not create
duplicate editions, and a revision must not overwrite an edition observed by
another writer.

The runtime is still a loopback-only developer preview. `X-Actor-Id` and
`X-Purpose` remain declarations used by the existing purpose-bound preview;
they are not authentication or tenant authorization. Keyverse integration is
therefore an explicit deployment gate, not an implied property of this API.

## Decision

1. Add `/v1/policy-documents` and `/v1/policy-gaps` routes with strict Pydantic
   request models, bounded fields, deterministic keyset pagination, and an
   OpenAPI-visible request/response contract.
2. Require `Idempotency-Key` on version-one mutations. Persist the validated
   request digest and response in `idempotency_record`, scoped to the local
   purpose actor, operation, and target policy for revisions. A reused key
   with a different body is a conflict; an exact retry replays the original
   response, including after a concurrent unique-key reservation race.
3. Return a strong `ETag` for a policy representation. Version publication
   requires `If-Match` with the current ETag (or `*`) and returns `428` when the
   precondition is missing or `412` when it is stale.
4. Return version-one errors as `application/problem+json` with RFC 9457
   problem members, a request reference, and no reflected request values.
5. Mark the unversioned policy routes deprecated in OpenAPI while retaining
   them for local compatibility. They are not removed in this slice.

## Consequences

The buyer can integrate a bounded policy/control truth surface and safely retry
authoring or revision requests. Paged policy reads batch related rows, and
validation problems avoid reflecting arbitrary field names or query values.
Existing CLI, officer-console, and preview HTTP callers continue to work.
Cursor semantics and idempotency records are now durable, but production
exposure remains blocked until Keyverse identity, tenant authorization,
migration rehearsal, and authenticated contract tests are complete.

## References

- Nottingham, M., Wilde, E., & Dalal, S. (2023). *Problem details for HTTP
  APIs* (RFC 9457). RFC Editor. https://www.rfc-editor.org/rfc/rfc9457.html
- Fielding, R., et al. (2022). *HTTP semantics* (RFC 9110). RFC Editor.
  https://www.rfc-editor.org/rfc/rfc9110.html
- Fielding, R., et al. (2022). *HTTP caching* (RFC 9111). RFC Editor.
  https://www.rfc-editor.org/rfc/rfc9111.html
