# ADR 0007: Publish Keyverse Bearer security on the GRC OpenAPI contract

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0005, ADR 0006

## Context

Issue #4 requires a published OpenAPI security scheme so standalone and modular
deployments present the same Keyverse contract. PR #55 already verifies Bearer
tokens at runtime. The generated `/openapi.json` still treated officer routes as
unauthenticated, which would let a consumer treat local preview headers as the
production identity model.

## Decision

1. `/openapi.json` publishes `KeyverseBearer` as HTTP bearer `at+jwt`.
2. Officer policy, evidence, and home operations declare the matching
   `grc.policy.read`, `grc.policy.write`, or `grc.evidence.write` scope.
3. `/healthz` and official catalog reads remain unmarked. Local preview without
   a verifier still accepts declared actor headers; the scheme is the production
   contract, not a remote-exposure switch.

## Consequences

Consumers can generate clients that send Keyverse access tokens. Remote traffic
stays denied until deployment hardening. This is not a second identity provider.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068
