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
2. `create_app` fails closed unless a Keyverse access-token verifier is injected.
   Declared `X-Actor-Id` headers cannot satisfy this start.
3. The process binds TLS using `CWL_GRC_TLS_CERTFILE` and `CWL_GRC_TLS_KEYFILE`.
   HTTP, including `/healthz`, returns 503. `X-Forwarded-Proto` is not TLS.
4. The bind remains `127.0.0.1`. Forwarded and non-loopback traffic stay 503.
   Unset, the developer preview is unchanged.

## Consequences

A hardened start cannot boot on header identity or cleartext HTTP. This is not
remote production exposure, Keyverse discovery at request time, or a substitute
for independent review.

## References

Rescorla, E. (2018). *The transport layer security (TLS) protocol version 1.3*
(RFC 8446). RFC Editor. https://www.rfc-editor.org/rfc/rfc8446
