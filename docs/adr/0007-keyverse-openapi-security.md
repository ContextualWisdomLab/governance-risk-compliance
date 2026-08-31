# ADR 0007: Publish Keyverse Bearer security on the GRC OpenAPI contract

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0005, ADR 0006

## Context

Issue #4 requires a published OpenAPI security scheme so standalone and modular
deployments present the same Keyverse contract. PR #55 verifies Bearer tokens at
runtime. Protected policy and evidence state must not be server-rendered before
Keyverse authorization, but a top-level browser navigation cannot attach an
`Authorization` header before the officer can reach the token-entry surface.
Treating `GET /` itself as Bearer-only therefore made the browser flow
unreachable.

## Decision

1. `/openapi.json` publishes `KeyverseBearer` as HTTP bearer `at+jwt`.
2. Policy reads and mutations, policy-gap reads, evidence mutations, and officer
   form posts declare the matching `grc.policy.read`, `grc.policy.write`, or
   `grc.evidence.write` scope.
3. `GET /` is a data-free browser bootstrap when a Keyverse verifier is
   configured. It renders no officer, tenant, policy-gap, or evidence-coverage
   state. The browser presents the Keyverse token locally and loads protected
   policy gaps only through the Bearer-authorized `/policy-gaps` API.
4. A successful browser mutation refreshes protected state through the same
   Bearer-authorized API instead of navigating to an Authorization-less
   server-rendered home page.
5. `/healthz`, the data-free bootstrap, and official catalog reads remain
   unmarked in OpenAPI. Local preview without a verifier still accepts declared
   actor headers; this exception is a browser bootstrap contract, not a remote
   exposure switch or a second identity path.

## Consequences

A compliance officer can reach the local browser shell without weakening the
resource-server boundary. Tenant- and actor-owned policy state still requires a
verified Keyverse access token and is never embedded in the unauthenticated
bootstrap response. Consumers can generate clients that send Keyverse access
tokens to protected APIs. Remote traffic stays denied until deployment
hardening. This is not a second identity provider.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068
