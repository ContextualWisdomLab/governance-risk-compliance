# Non-reflecting request validation responses

Status: **Proposed**. GRC #69; continuation of PR #70 on
`7bbfbf9f4e7f9a7916852a071c65a86d7d0be9cb`, not a new identity or privacy engine.
No numeric ADR is reserved while other owner stacks are in flight.

## Problem and evidence

The local request boundary rejects an untrusted browser context, but a valid
local request can still fail body or form validation. At the inspected head,
`create_app` did not register a custom `RequestValidationError` handler.
FastAPI's default response can include rejected values in `detail[].input` and
caller-selected dictionary keys in `detail[].loc`. Both are unnecessary copies
of data that may contain personal information. This finding is unintended
reflection, not evidence that another user's data was disclosed or a real
privacy incident occurred.

A real FastAPI application using the production evidence input type
`dict[str, str]` reproduced three failing non-reflection assertions. A broader
contract suite produced nine failures and one passing compatibility case before
the custom handler was added. Fixtures contain synthetic unit-test strings only.
No customer request, credential or personal record was used.

## Decision and alternatives

Add `validation_error_response` to the existing HTTP privacy boundary module
and register it for `RequestValidationError` in the actual `create_app` factory.
Return a single bounded 422 diagnostic using the existing `detail` list shape:

```json
{"detail":[{"type":"request_validation_failed","loc":[],"msg":"Check required fields and data types against the API schema."}]}
```

Do not serialize `errors()`, the request body, exception text, rejected values,
error context, arbitrary keys, URLs or headers. Do not log them in the handler.
The handler sets `Cache-Control: no-store`; the existing middleware adds the
remaining response protections. Valid requests retain their exact payload and
existing purpose/authorization checks. Invalid requests do not reach the route
mutation handler. No new dependency, network call, database object or CORS rule
is needed.

Removing only `input` is rejected because `loc` can carry a private dictionary
key. Passing raw validator messages through an HTML escaping function is
rejected: escaping is not data minimization. A heuristic PII detector is rejected
because arbitrary values and new data types would escape it. A field allowlist
may be added later only with schema-version-bound static labels and tests; this
preview has no such label contract. The chosen response deliberately trades
field-specific diagnostics for a bounded, non-reflecting failure message.

## Compatibility and ownership

HTTP status 422 and the structural `detail`/`type`/`loc`/`msg` response shape
remain. Per-field Pydantic error types and locations are no longer returned.
Clients must not rely on reflected validator internals; use the published API
schema to correct required fields and types. Ordinary HTTP exceptions and
valid evidence responses are unchanged. This does not promise control over
outer server errors, database/driver logs, reverse-proxy logs or other services.

This is a narrowly scoped fix in an existing Python framework adapter, not a
new Python security core or authorization implementation. The parent
[request-boundary ADR](privacy_request_boundary.md) retains the Rust target and
replacement/release conditions. A future Rust HTTP adapter must pass these same
non-reflection and valid-payload contracts before removing the legacy adapter.
GRC owns its HTTP responses; Keyverse still owns identity, and other services
must fix equivalent defects at their own canonical boundaries.

PIPA Article 29 and the access-protection objective of Safety Measures Notice
No. 2026-9 Article 6 motivate this engineering control. They do not mandate this
JSON format or establish compliance from a passing test. Source verification,
organizational applicability and operational closure are distinct; see
[the source register](../../doctoring/privacy_law_sources.md).

## Verification and delivery gate

The source-subset suite runs the unchanged original 115 boundary cases plus
10 validation-privacy cases through real FastAPI validation. Result: 125 passed;
changed `remote_access.py` has 122/122 statements and 56/56 branches covered,
with 10/10 module/class/function docstrings. Python 3.12 grammar parsing passes;
execution used Python 3.13.5, FastAPI 0.128.2 and Starlette 0.50.0, not the locked
repository installation. Six additional `create_app` route cases are provided
for the complete Product suite. Their execution must be verified on the new head.

Predecessor head `7bbfbf9` has successful hosted Product, Security Scan and SAST
Semgrep runs. CodeQL compatibility reported a pending central dispatch verdict,
not a source vulnerability. None of those results transfer to a new commit.
Keep Draft until fresh required checks and independent review meet live rules;
release and deployed/organizational evidence remain separate conditions. Do not
close #69 or discard the existing identity/applicability stacks from this repair.
