# Keyverse insufficient-scope HTTP status

## Decision

A verified Keyverse access token that lacks an action-specific GRC scope is
authorization failure, not authentication failure. `require_access_scopes`
raises `AccessTokenScopeError`, a subclass of `AccessTokenValidationError`.
The HTTP adapter maps that type to 403 and every other validation failure to
401. Officers presenting a signed token without `grc.policy.write` or
`grc.evidence.write` should see that the token is recognized and that this
action is not granted, then request the missing scope from Keyverse.

Do not classify 403 vs 401 by searching exception text for `"required scope"`.
Rewording the message must not change the status.

## Standards rationale

RFC 6750 section 3.1 uses `invalid_token` for 401 and `insufficient_scope`
for 403 after the token itself has been authenticated. RFC 9068 keeps GRC a
resource server that consumes Keyverse access tokens. RFC 9700 requires
resource and action restriction without collapsing those two outcomes.

## Verification contract

- `require_access_scopes` raises `AccessTokenScopeError`.
- `authenticate_keyverse_request` returns 403 for `AccessTokenScopeError`
  even when the message does not contain `"required scope"`.
- Missing, malformed, or unsigned Bearer material remains 401.
- Officer evidence form authenticates before `control_ref` validation so an
  unauthenticated caller cannot probe catalog well-formedness (401, not 400).
- Officer home `fetch` sends Bearer only when a Keyverse token is present.
  Local preview without a verifier sends `X-Actor-Id` from the officer
  identifier so browser authoring remains usable.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access
tokens* (RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068

Jones, M. B., & Hardt, D. (2012). *The OAuth 2.0 authorization framework:
Bearer token usage* (RFC 6750). Internet Engineering Task Force.
https://doi.org/10.17487/RFC6750

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current
practice for OAuth 2.0 security* (RFC 9700, BCP 240). RFC Editor.
https://www.rfc-editor.org/rfc/rfc9700
