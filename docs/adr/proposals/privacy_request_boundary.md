# Local preview request authority and privacy boundary

Status: **Proposed**. Tracked by GRC issue #69. No numeric ADR is reserved across
unmerged owner stacks; assign a number after the then-current ADR inventory and
owner review. This record is not Accepted merely because a local test is green.

## Problem and observed evidence

At protected `develop@529cf321f134e26c0cd379ee53c06ab5297363b6`, the application
checks a loopback connection peer and the truthiness of two forwarding values.
The `/officer/policy` and `/officer/evidence` handlers accept browser form data.
A local connection is not proof that the user intended a mutation: a browser
visiting another origin can initiate requests toward a local service. An
arbitrary HTTP authority also need not be the intended loopback application.

The fetched `app.py` and `remote_access.py` blobs were verified as
`26f3f760fe5e9286038251e1962a072f264a662d` and
`f7eb3e8071ea02caf57cba99258233e9fcaa5a27`. A source-extracted execution of the
original middleware reached the downstream sentinel in five cases that must
be rejected: external Origin, null Origin, external Host, present-empty
Forwarded, and an originless form. This is reproducible source-level RED
evidence, not a claim of an actual customer incident or a browser exploit.

PIPA Article 29 and Safety Measures Notice No. 2026-9 Article 6 supply the
safeguard/access-control requirement. They do not prescribe these HTTP header
names. OWASP's CSRF guidance supplies the implementation rationale. See
[primary sources](../../doctoring/privacy_law_sources.md).

## Decision and rejected alternatives

Repair the existing preview boundary before adding personal-data workflows.
`PreviewBoundaryMiddleware` is a stateless pure-ASGI boundary; `create_app`
registers it before routes. No body is read, buffered, logged, masked or changed
by the guard. GRC policies, evidence and database semantics are otherwise
unchanged, and the remote-access prohibition remains in force.

A peer-only check is rejected because it does not bind browser intent. A
TrustedHost-only middleware is rejected because it does not compare the full
Origin scheme/host/port or distinguish browser form requests. Replacing the
entire GRC identity stack in this security repair is rejected: #38 and its
successors retain their valid work and their independent integration gates.
Adding CORS permissions or a remote-preview environment switch is rejected.

## Request contract

1. Nonlocal, absent or malformed peers fail with the existing generic 503.
   Any `Forwarded`, `Via`, `X-Real-IP` or `X-Forwarded-*` header is proxy evidence,
   even when empty. Header name case does not bypass duplicate detection.
2. Require one bounded literal local Host: `localhost` or an IP literal whose
   address is loopback. `testserver` is accepted only for the existing in-process
   `testclient` peer, never for a real network peer. No DNS lookup authorizes a
   host. Scheme, default port and IPv6 representations are normalized; distinct
   hostnames, schemes and ports are not collapsed into the same origin.
3. Present Origin and Referer must each match the target origin. Null, empty,
   duplicated, contradictory, credential-bearing, control-character-bearing,
   oversized or ambiguous values fail with a generic 403. Origin is origin-only;
   a Referer may include a resource path and query.
4. Present Fetch Metadata must be `same-origin` or `none`; this intentionally
   rejects `same-site` too in a local-only developer preview. An invalid Origin
   cannot fall back to a Referer or an explicit client marker.
5. Without Origin/Referer, allow safe methods, a `same-origin` Fetch Metadata
   assertion, or an intentional non-simple client request (`application/json`
   or `X-CWL-Preview-Request: 1`). Browser CORS is not enabled, so these non-simple
   requests cannot use a cross-origin preflight to acquire authority. Originless
   simple form/text mutations fail closed. The client marker is **not a secret,
   authentication, tenant authorization or legal basis**.
6. Emit `Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy:
   same-origin`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and an
   additional restrictive CSP for responses traversing this middleware.
   Preserve any separate upstream CSP. Preserve response body frames and
   lifespan; reject unsupported WebSocket sessions.

## Compatibility and limitations

`Referrer-Policy: same-origin` suppresses referrers to other origins while
preserving native same-origin form Origin. The initial `no-referrer` candidate
was rejected during standards review: WHATWG Fetch section 3.2 nulls the Origin
of navigate-mode POSTs under that policy. A failing regression for this setting
preceded its repair. Do not solve the conflict by trusting arbitrary null Origin.


Existing same-origin forms now carry an explicit Origin in their tests. Local
JSON API calls retain their declared-purpose contract. No auto-added test
header globally hides the new negative cases. Public `request_is_local` keeps
its call signature while treating empty forwarding as present.

This does not authenticate local processes, defend an already compromised host
or an undetectable local proxy, or make the preview suitable for customer PII.
A request marker can be forged by a native program. Exceptions handled outside
this middleware by Starlette's outer ServerErrorMiddleware are not claimed to
receive the response headers. Full application and deployed-proxy/browser tests
remain mandatory; source-subset tests are not a substitute.

This narrow Python source repair removes a defect in an existing Python
runtime; it is not a new Python service or the chosen long-term security core.
The target remains a Rust-owned request/policy boundary. Remove this legacy
implementation only after the replacement is released, integrated with verified
Keyverse identity and tenant authorization, and passes the same hostile/positive
contract, real-browser tests and rollback rehearsal. Do not delay an existing
source defect until a wholesale rewrite, and do not create a second permanent
policy authority. Framework constructor `app` and ASGI keys retain their
external contract spelling; internal names use multiword identifiers.

## Verification and release decision

The original behavioral RED and the new positive/negative tests precede this
implementation. The isolated guard suite passed 115 cases with
117/117 statements and 56/56 branch destinations covered. Coverage is scoped
to `cwl_grc/remote_access.py`, not the whole repository. A separate real-GRC
route suite checks persisted policy state and exact evidence values. Existing
form tests retain all their domain assertions and add only same-origin context.

Before protected merge, re-run the full locked Product suite, security lanes,
independent review and current-head checks. Before operational closure, verify
an immutable release and deployed controls. #69 stays open for the broader
privacy obligations. No ruleset changes, scanner substitutions, force push,
self-approval or destruction of previous PR work are authorized by this ADR.

A real Chromium 144.0.7559.96 test was attempted against isolated localhost
unit handlers using this middleware. Navigation was blocked by the managed
browser with `net::ERR_BLOCKED_BY_ADMINISTRATOR` before the first page loaded.
This is not a functional browser RED/GREEN result. No browser policy was disabled
or bypassed. Real-browser validation remains an explicit pre-release gap.

The modified operator-test file no longer republishes its three fixed Fernet key literals. Each test context generates ephemeral key material using the existing cryptography dependency. This is test-only credential hygiene, not a production key-management implementation.
