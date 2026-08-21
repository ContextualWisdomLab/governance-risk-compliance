# ADR 0003: Verify a closed Keyverse JWT access-token profile before route integration

## Status

Accepted for the first authentication prerequisite of issue #4. This ADR does not authorize remote deployment.

## Context

The first GRC slice records `X-Actor-Id` and `X-Purpose` as local audit declarations. Those headers do not prove identity and cannot become a production authorization boundary. Keyverse owns CWL identity, OIDC/OAuth federation, relying-party desired state, and account lifecycle; CWL GRC must remain a resource server and policy-enforcement point rather than copy Keyverse credentials or account tables.

OpenID Connect ID Tokens and OAuth access tokens can both use JWT syntax. RFC 9068 requires an explicit `at+jwt` access-token type, signature validation, exact issuer and resource audience checks, and the `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and `client_id` claims. RFC 9700 requires resource- and action-restricted access tokens and warns about confusing a client identity with a resource-owner identity. Accepting a token merely because its signature is valid would therefore be insufficient.

Keyverse currently uses closed relying-party profiles with an exact audience and bounded `role`, `org`, and `workspace` claims. GRC also needs an explicit principal kind so a human policy-authoring token cannot be confused with a service token.

## Decision

1. Add a provider-neutral verification kernel without yet changing FastAPI route access or the local-only network boundary.
2. Accept only compact signed JWT access tokens whose protected header has:
   - `alg=RS256`;
   - `typ=at+jwt` or `application/at+jwt`;
   - one non-empty `kid`;
   - no `crit` header.
3. Require exact configured issuer and resource audience plus the RFC 9068 claims `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and `client_id`.
4. Require the closed Keyverse claims `scope`, `role`, `org`, `workspace`, and `principal_kind`.
5. Interpret:
   - `sub` as the verified actor identifier;
   - `org` as the tenant identifier;
   - `workspace` as the GRC workspace reference;
   - `role` through an explicit resource-server allowlist;
   - `scope` as the RFC 6749 space-delimited action authorization set.
6. Limit this first profile to `principal_kind=human`. Reject service principals rather than infer grant type from `sub` or `client_id`. A later profile must give service principals a distinct contract and authorization path.
7. Reject tokens where `sub == client_id` in this first human profile to prevent client/resource-owner confusion.
8. Load only a bounded reviewed public JWK document:
   - maximum 1 MiB;
   - non-empty unique `kid` values;
   - `kty=RSA`, `use=sig`, `alg=RS256`;
   - no RSA private parameters;
   - multiple eligible keys permitted for controlled rotation overlap.
9. Do not fetch discovery metadata or JWKs over the network in this slice. Offline key input cannot silently introduce SSRF, redirects, unbounded responses, or runtime issuer drift.
10. Keep Keyverse as the issuer and relying-party authority. GRC stores no password, passkey, client secret, refresh token, raw bearer token, or Keyverse administrator credential.
11. Add an explicit `require_access_scopes` policy primitive. Authentication alone never authorizes a GRC action.
12. Accept an optional caller-owned atomic JTI replay guard. Without that guard, this offline kernel preserves normal reusable bearer-token semantics; it does not create an unsafe process-local replay cache.
13. Keep remote traffic disabled until tenant-owned persistence, route dependencies, OpenAPI security, discovery/JWK refresh, service-principal handling, and deployment acceptance tests are complete.

## Consequences

A forged issuer, wrong audience, ID token, unsigned token, unsupported algorithm, unknown key, malformed or private JWK, expired/future token, unauthorized client or role, invalid tenant/workspace, and missing action scope fail closed before producing an `AuthenticatedPrincipal`.

Reviewed old and new public keys can coexist during a rotation window. Removing the old key from the reviewed set revokes its future acceptance on the next verifier construction. This is configuration-level rotation evidence, not yet a live discovery or cache-refresh implementation.

The verifier is intentionally independent of FastAPI and SQLAlchemy. Later route and tenant-storage slices can consume the same typed principal without changing cryptographic validation semantics.

The optional replay guard lets a route or durable authorization service enforce one-time use where its action contract requires it. The guard receives the verified `jti` and must perform an atomic check-and-record operation; the verifier does not retain token state itself.

The strict RFC 9068 `client_id` requirement may require a Keyverse relying-party mapper or issuer configuration because vendor-native tokens often expose `azp` instead. GRC does not alias `azp` to `client_id`; the issuer profile must converge to the reviewed contract.

## Rejected alternatives

- **Trust `X-Actor-Id` or `X-Purpose`:** caller assertions are not authentication.
- **Accept any JWT with a valid signature:** enables ID-token/access-token and cross-resource confusion.
- **Choose the algorithm from the token header:** permits algorithm substitution; the resource server fixes `RS256`.
- **Accept `azp` as an undocumented `client_id` fallback:** weakens the standardized profile and hides issuer drift.
- **Infer human versus service from `sub == client_id`:** RFC 9700 identifies this namespace confusion as unsafe; the profile requires an explicit principal kind and currently accepts humans only.
- **Fetch arbitrary discovery/JWKS URLs immediately:** widens the network and rotation boundary before URL pinning, response bounds, cache semantics, and outage behavior have tests.
- **Store raw bearer tokens for audit:** creates replayable credential material; audit records should store verified opaque identifiers such as `jti`, actor, client, tenant, and the authorization decision.
- **Create a process-local replay cache:** it is not correct across workers or restarts; use the optional JTI guard with a durable atomic store when one-time use is required.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens* (RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current practice for OAuth 2.0 security* (RFC 9700, BCP 240). RFC Editor. https://www.rfc-editor.org/rfc/rfc9700

OpenID Foundation. (2023a). *OpenID Connect Core 1.0 incorporating errata set 2*. https://openid.net/specs/openid-connect-core-1_0-errata2.html

OpenID Foundation. (2023b). *OpenID Connect Discovery 1.0 incorporating errata set 2*. https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
