# ADR 0009: Require Keyverse and TLS before a hardened local start

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0005, ADR 0008

## Context

Issue #4 forbids using declared actor headers as a production identity model.
PR #55 and PR #56 authenticate Keyverse when a verifier is injected, but
`python -m cwl_grc` and `cwl-grc serve` still start an HTTP loopback preview
without one. Operators could mistake that header-identity start for customer
admission.

Remote exposure remains forbidden. Encrypted transport must be admitted on
loopback before any later remote bind.

## Decision

1. `CWL_GRC_REQUIRE_KEYVERSE=1` (or `true`/`yes`) is the hardened local start.
   `0`/`false`/`no`/unset keep the developer preview. Any other nonempty value
   fails closed instead of booting header-identity HTTP.
2. `create_app` fails closed unless a Keyverse access-token verifier is injected.
   Declared `X-Actor-Id` headers cannot satisfy this start. Standalone
   `cwl-grc serve` and `python -m cwl_grc` load a reviewed offline JWKS from
   `CWL_GRC_KEYVERSE_JWKS_PATH` plus issuer, audience, and client identifiers.
   They do not discover Keyverse on the network or admit remote traffic.
3. The process binds TLS using readable `CWL_GRC_TLS_CERTFILE` and
   `CWL_GRC_TLS_KEYFILE` paths. Empty or missing files fail closed before
   Uvicorn starts. HTTP, including `/healthz`, returns 503. `X-Forwarded-Proto`
   is not TLS. Uvicorn `proxy_headers` is disabled so a loopback client cannot
   rewrite the ASGI scheme. Hardened-start next actions also name
   `CWL_GRC_EVIDENCE_KEY` for persistent stores.
4. The bind remains `127.0.0.1`. Forwarded, forwarded-proto, forwarded-host, and
   non-loopback traffic stay 503. Unset, the developer preview is unchanged.

## Consequences

A hardened start cannot boot on header identity or cleartext HTTP. This is not
remote production exposure, Keyverse discovery at request time, or a substitute
for independent review.

## References

Rescorla, E. (2018). *The transport layer security (TLS) protocol version 1.3*
(RFC 8446). RFC Editor. https://www.rfc-editor.org/rfc/rfc8446
