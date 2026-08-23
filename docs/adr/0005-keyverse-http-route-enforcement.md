# ADR 0005: Enforce Keyverse access tokens on GRC HTTP routes

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0003, ADR 0004

## Context

ADR 0003 and ADR 0004 give CWL GRC a closed RFC 9068 access-token profile and a
bounded OIDC/JWKS loader. HTTP routes still treated `X-Actor-Id` as the actor.
Those headers are local preview declarations, not authentication. Keyverse remains
the identity issuer; GRC is a resource server.

## Decision

1. `create_app(access_token_verifier=...)` is the Keyverse adapter. When the
   verifier is absent, the local developer preview keeps declared actor/purpose
   headers and loopback denial.
2. When a verifier is present, policy and evidence routes require a Bearer
   access token. The verified `sub` is the actor. `X-Actor-Id` cannot override
   it. A declared `X-Tenant-Id` must match the Keyverse `org` claim.
3. Action scopes are `grc.policy.read`, `grc.policy.write`, and
   `grc.evidence.write`. Missing scopes raise `AccessTokenScopeError` and
   return 403 (`insufficient_scope`); other validation failures return 401.
   HTTP status is selected from the exception type, not from matching the
   exception text.
4. Policy list, gap queries, and the officer home (`GET /`, `POST /officer/policy`,
   `POST /officer/evidence`) return or mutate only documents authored by the
   verified subject. Official catalog reads remain unauthenticated because they
   are published control identifiers, not tenant records.
5. `/healthz` remains unauthenticated. Remote traffic stays denied until
   deployment hardening.
6. Officer home HTML forms cannot attach an `Authorization` header on native
   submit. When a Keyverse token is present, the page stores it in
   `sessionStorage` and sends Bearer on `fetch`. Local preview without a
   verifier sends `X-Actor-Id` from the officer identifier instead of requiring
   a token. Evidence form posts authenticate before validating `control_ref`.

## Consequences

Officers can author CSAP-mapped policies under a Keyverse subject without GRC
storing passwords or refresh tokens. Local preview tests continue to run without
a verifier. This still does not authorize remote production exposure.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068

Jones, M. B., & Hardt, D. (2012). *The OAuth 2.0 authorization framework:
Bearer token usage* (RFC 6750). Internet Engineering Task Force.
https://doi.org/10.17487/RFC6750

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current
practice for OAuth 2.0 security* (RFC 9700). RFC Editor.
https://www.rfc-editor.org/rfc/rfc9700
