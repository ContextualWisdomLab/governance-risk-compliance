# ADR 0004: Load Keyverse OIDC metadata and JWKs through a bounded pinned-HTTPS port

## Status

Accepted for the second authentication prerequisite of issue #4. This ADR does not authorize route integration or remote deployment.

## Context

ADR 0003 fixes the cryptographic and claim contract for Keyverse JWT access tokens, but an operational resource server also needs issuer metadata and public signing keys. OpenID Connect Discovery derives the provider configuration URL from the issuer and requires the returned `issuer` value to match exactly. A naïve HTTP client that follows redirects, accepts an arbitrary `jwks_uri`, re-resolves the hostname while connecting, or reads an unbounded response would create SSRF, DNS-rebinding, memory-pressure, and issuer-drift paths inside the authentication boundary.

Key rotation also needs an atomic snapshot: a partially validated refresh cannot replace the last known-good metadata and JWK set, and an older refresh result cannot overwrite a newer one. The loader must retain byte-level source evidence without storing a bearer token, client secret, or Keyverse administrator credential.

## Decision

1. Keep metadata/JWK retrieval behind the `KeyverseDocumentFetcher` port. The provider loader consumes only a prevalidated `ValidatedHttpsEndpoint`; alternative transport implementations must preserve the same invariants.
2. Construct the OpenID Provider Configuration URL by appending `/.well-known/openid-configuration` after the exact issuer path.
3. Require an exact HTTPS issuer with no userinfo, query, or fragment.
4. Accept a JWK endpoint only when its normalized host is present in a closed resource-server allowlist. Do not infer an allowlist from discovery output.
5. Reject local naming conventions, non-global IP literals, malformed ports, path traversal, backslashes, encoded slash/backslash delimiters, and control characters.
6. Resolve each endpoint once per load, reject the entire result when any answer is malformed or non-global, deduplicate addresses, and dial only the pinned addresses returned by that validation.
7. Preserve the original hostname for TLS SNI and HTTP `Host` while dialing a pinned IP address. Use the platform trust store and hostname verification.
8. Use one `GET` request with `Accept: application/json`, `Accept-Encoding: identity`, a fixed product user agent, and no redirect behavior.
9. Require HTTP 200 and media type `application/json`. Bound both declared `Content-Length` and streamed bytes. Default bounds are 64 KiB for metadata and 1 MiB for JWKs; reviewed configuration may raise them only within the hard ceilings of 1 MiB and 4 MiB respectively.
10. Require discovery metadata to:
    - be a JSON object;
    - return an `issuer` byte-for-byte equal to the configured issuer string;
    - name one non-empty `jwks_uri`;
    - expose a non-empty string array in `id_token_signing_alg_values_supported`;
    - advertise `RS256`.
11. Validate the JWK document through ADR 0003’s public-RSA-signing-key parser. Old and new keys may coexist during a reviewed rotation window.
12. Record SHA-256 references for the exact metadata and JWK bytes and an aware UTC `loaded_at` time.
13. Replace the active provider snapshot atomically only when the new snapshot has the same issuer and a strictly later `loaded_at` value. A failed, stale, or cross-issuer refresh leaves the previous snapshot intact.
14. Keep provider loading independent of FastAPI routes and tenant persistence. Remote traffic remains disabled until the complete issue #4 boundary is implemented and accepted.

## Consequences

The authentication subsystem can obtain exact issuer metadata and public keys without granting discovery output authority over arbitrary network destinations. DNS answers are pinned for the request while TLS continues to authenticate the reviewed hostname. Redirects, compressed responses, invalid media types, oversized documents, private addresses, and stale refreshes fail closed.

The loader deliberately rejects deployments whose Keyverse JWK endpoint is not on the configured allowlist. When Keyverse and GRC are placed on a private network in a future reviewed deployment, the URL policy must be extended with explicit private-network identities and network-bound acceptance tests rather than weakening the global-address rule implicitly.

The current snapshot registry is process-local. Durable rotation receipts, refresh scheduling, outage SLOs, key-retirement policy, and multi-process synchronization remain later work. A valid snapshot alone does not authorize a route or a tenant operation.

## Rejected alternatives

- **Use an ordinary redirect-following HTTP client:** permits destination changes after validation.
- **Trust any `jwks_uri` returned by discovery:** grants untrusted metadata network authority.
- **Validate DNS and reconnect by hostname:** permits a second resolution and DNS rebinding.
- **Disable hostname verification when dialing an IP:** loses the issuer’s TLS identity.
- **Accept compressed or unbounded responses:** weakens byte accounting and memory safety.
- **Replace the active key set before all validation succeeds:** creates partial-refresh authentication failures.
- **Accept a different issuer after refresh:** enables silent trust-domain migration.

## References

Internet Engineering Task Force. (2022). *Recommendations for secure use of transport layer security (TLS) and datagram transport layer security (DTLS)* (RFC 9325, BCP 195). RFC Editor. https://www.rfc-editor.org/rfc/rfc9325

OpenID Foundation. (2023). *OpenID Connect Discovery 1.0 incorporating errata set 2*. https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
