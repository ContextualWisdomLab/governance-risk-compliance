# ADR 0008: Attribute audit events to Keyverse issuer, client, and request correlation

- Status: Accepted
- Date: 2026-08-23
- Issue: #4
- Depends on: ADR 0005, ADR 0006

## Context

Issue #4 requires every policy and evidence action to be attributable to a
verified Keyverse principal. ADR 0005 authenticates the HTTP actor. ADR 0006
stamps `tenant_identifier` on owned rows. `audit_event` still recorded only
actor, purpose, and tenant. That is not enough to join an officer action to the
issuing Keyverse realm, OAuth client, and request correlation without copying
the access token.

CWL GRC is a resource server. It must not persist bearer tokens, refresh
tokens, or compact JWT material. Correlation is a request identifier, not a
token identifier (`jti`).

## Decision

1. Persist `issuer_identifier`, `client_identifier`, `correlation_reference`,
   and `decision_outcome` on `audit_event`.
2. When a Keyverse verifier is configured, stamp the verified issuer and
   `client_id` from the access-token profile. Local preview without a verifier
   uses `local_preview`.
3. Bind `X-Request-ID` when it is an exact safe token; otherwise generate a
   correlation reference. Compact JWT material is never stored.
4. Authorized mutations record `decision_outcome=allow`. Denied authentication
   does not write an audit row and does not persist the bearer.
5. Upgrade existing stores with migration `0003_audit_attribution`. Legacy rows
   receive `local_preview` issuer/client, `legacy_unattributed` correlation, and
   `allow`.

## Consequences

Officers can join a CSAP-mapped policy or evidence action to Keyverse issuer,
client, tenant, subject, purpose, and request correlation. This still does not
authorize remote production exposure. Deployment-hardening runbooks remain
operator documentation for local preview until encrypted transport and
Keyverse-backed admission exist.

## References

Bertocci, V. (2021). *JSON Web Token (JWT) profile for OAuth 2.0 access tokens*
(RFC 9068). RFC Editor. https://www.rfc-editor.org/rfc/rfc9068

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current
practice for OAuth 2.0 security* (RFC 9700). RFC Editor.
https://www.rfc-editor.org/rfc/rfc9700
