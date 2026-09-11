# ADR 0010: Require Keyverse tokens for hardened CLI writes

- Status: Accepted
- Date: 2026-08-24
- Issue: #4
- Depends on: ADR 0005, ADR 0009

## Context

Issue #4 forbids treating declared actor identifiers as authentication.
ADR 0009 fails closed for `cwl-grc serve` and `python -m cwl_grc` when
`CWL_GRC_REQUIRE_KEYVERSE` is set, but `policy author`, `policy revise`, and
`bind` still accepted `--actor` as the writer. Officers could believe the
hardened local start protected every GRC mutation surface.

Remote exposure remains forbidden. This decision is loopback-only.

## Decision

1. When `CWL_GRC_REQUIRE_KEYVERSE` is set, CLI data commands authenticate
   `CWL_GRC_ACCESS_TOKEN` through the same reviewed offline JWKS used by serve.
   `--actor` is not identity. A matching value is tolerated; a mismatch is
   impersonation and fails closed.
2. `policy author`, `policy revise`, and `bind` require the write scopes already
   published on HTTP. `policy list` and `gaps` require `grc.policy.read` and
   return only the verified officer's tenant-owned rows.
3. Ordinary preview remains `--actor` plus purpose. Invalid flag values still
   fail closed instead of falling back to declared-actor writes.
4. This is not remote customer admission.

## Consequences

A hardened local operator cannot mutate policy or evidence through the CLI
without a Keyverse access token. Independent review is still required before
any non-loopback bind.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068
