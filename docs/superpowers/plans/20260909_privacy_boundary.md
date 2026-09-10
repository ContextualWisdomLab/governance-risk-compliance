# Privacy request boundary repair

Goal: close the existing local-preview HTTP trust gap without enabling remote access or claiming statutory compliance.
Architecture: preserve the existing loopback classifier; add a request-origin/authority decision in the same owner module and register a pure ASGI boundary before GRC handlers. Successful and denied HTTP responses carry no-store and same-origin referrer protections. Identity, retention and legal applicability remain separate owner work.
Spec: `docs/adr/proposals/privacy_request_boundary.md`; approved execution scope: GRC issue #69 and the user's 2026-09-09 instruction.

## Constraints
- Protected baseline: 529cf321f134e26c0cd379ee53c06ab5297363b6; fetch each modified file before changing it.
- Never replace existing feature-stack deltas. No force push, direct protected write, self-approval, raw PII, added secret, permission widening or new workflow.
- This is a causal repair to an existing Python boundary, not a new Python service. The Rust migration target and deletion conditions belong in the Proposed ADR.
- Keep original policies/evidence bytes unchanged. Header values are untrusted and must not be reflected or used as authenticated identity.
- Source subset tests are not full-product or deployed-environment verification.

## Task 1: reproduce the source defect
- [x] Hash-check the original `cwl_grc/app.py` and `remote_access.py` against GitHub blobs.
- [x] Execute the original middleware function extracted with Python AST (decorator removed only), using a sentinel downstream handler. Assert rejection of hostile Host/Origin and empty forwarding. Record the actual failures, never call the sentinel a database integration test.

## Task 2: enforce before dispatch
Files: `cwl_grc/remote_access.py`, `cwl_grc/app.py`, `tests/test_privacy_boundary.py`.
- [x] Write positive/negative ASGI tests: exact scheme/host/port, duplicate headers, literal loopback only, Fetch Metadata, Origin/Referer fallback, missing-origin form submission, JSON programmatic clients, cache policy, WebSocket rejection/lifespan behavior and unchanged payload bytes.
- [x] Implement `PreviewBoundaryMiddleware` in the existing owner module; integrate using `app.add_middleware(PreviewBoundaryMiddleware)`.
- [x] Preserve `/healthz`, local JSON APIs and browser same-origin forms. Deny unknown form origin unless the non-browser client supplies `X-CWL-Preview-Request: 1`; reject hostile Origin even with that marker.
- [x] Run `pytest tests/test_privacy_boundary.py`, statement/branch coverage for the entire changed boundary module, docstrings and compile checks.
- [x] Update existing officer form tests with explicit same-origin context; add actual `create_app` regression tests for hosted full-product verification.

## Task 3: trace, publish and re-read
- [x] Write Proposed ADR, legal crosswalk and operator instructions; distinguish current law, enacted future law and unverified subordinate rules.
- [ ] Coordinate related Keyverse/CO/data owners via existing issues where possible; preserve obligations as unverified until operational evidence exists.
- [ ] Publish a bounded PR against the fresh protected base via the GitHub connector.
- [ ] Re-read exact head, diff, checks and review. Retain Draft until full checks and independent review satisfy the live repository rules. Do not close #69 from this partial slice.

## Recorded validation boundary

The component suite passes 115 tests with all 117 statements and 56 branch destinations covered. Full-product route tests are committed for the normal Product lane, not claimed run in the source-subset workspace. Installed Chromium/Playwright could not navigate to localhost: `net::ERR_BLOCKED_BY_ADMINISTRATOR`; no browser execution or screenshot success is claimed, and managed policy was not bypassed.
