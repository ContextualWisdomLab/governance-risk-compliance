# Privacy continuation: validation response and evidence status

Observation date: 2026-09-10. Work parent:
`7bbfbf9f4e7f9a7916852a071c65a86d7d0be9cb` on GRC PR #70.
The PR remains a source proposal, not a deployment or legal-compliance assertion.

## Changes in this continuation

The FastAPI default request-validation response unnecessarily reflected
rejected values and caller-supplied dictionary keys. The new bounded 422 handler
is in the existing `cwl_grc/remote_access.py` and registered by `create_app`.
It never reads/serializes/logs validation material, retains no-store and leaves
valid payloads and existing authorization checks unchanged. See the
[Proposed decision](../adr/proposals/privacy_validation_response.md).

The source register now records selected-clause verification and applicability
review separately for every legal source. No automatic exemption or affirmative
compliance decision may arise from an unverified source. Existing protective
controls stay active; unknown applicability does not suspend the legal duty.
These are documentary verification states, not a newly shipped legal engine.

## Historical baseline interpretation (CodeRabbit 3970316438)

The archived `product_technical_gap_baseline_529cf321.md` retains Git blob
`d03b70b89ac30a579c31d66dd1a2dc4b9e697e34` without editing its historical rows.
Its 2026-08-24 header is a document-generation date, not evidence that every
embedded paragraph was observed on that date. In particular, the early #32/#33
paragraphs use older source heads as “current,” while the later queue records
them as closed stack-only merges. Those paragraphs are historical claims with
**individual observation time not established**. They must not drive current
PR-state, release, or deployment decisions.

Fresh GitHub metadata read on 2026-09-10 establishes:

| PR | State | Head returned by API | Merge commit | Merge time (UTC) | Target |
| --- | --- | --- | --- | --- | --- |
| #32 | closed, merged | `a86fb10cfcadd18769e5830d0982abea4e728bb5` | `7eab5bd272ca88850198f47a6c78313e3f7bd49e` | 2026-08-21T11:44:10Z | `feat/recovery-event-telemetry` |
| #33 | closed, merged | `6648cc7fc255ed6711275887ba5cd5e857073d41` | `8881d3966e3e9da29b8dce990a95295a2780618b` | 2026-08-21T11:45:58Z | `feat/internal-control-model` |

The older body/paragraph heads `c750cb8bdc347f4fc592e2e908f098520e16074f`
and `55afaee88fd0e9113a9fb655da1d2d95275c0e8c` are not the fresh API heads.
The #33-to-#32 parent relationship remains valid. A merge into either feature
branch does not establish integration into protected `develop` or deployment.
Keep all valid deltas and re-read their successor/integration evidence; do not
reopen, close or delete them merely to make a status table look consistent.

## Actual verification and remaining gates

Local RED: three assertions reproduce default validation reflection; the expanded
contract suite has nine failures before the handler and ten passes after it.
Combined GREEN: 125 tests pass, 122 statements and 56 branches in the changed
boundary module are fully covered, and all ten symbols have docstrings.
The tested source subset uses Python 3.13.5; Python 3.12 grammar is checked but a
3.12 runtime is not claimed. Six actual `create_app` route tests are added for
the full locked Product lane. Source-subset coverage is not repository coverage.

Predecessor `7bbfbf9` hosted runs:

| Workflow | Run | Observed result |
| --- | --- | --- |
| Product | 34370192978 | success |
| Security Scan | 34370193008 | success |
| SAST Semgrep | 34370192900 | success |
| CodeQL PR | 34370193003 | failure: compatibility job read `VERDICT_STATE: pending` |

The CodeQL Python compatibility log (job 102530203658) says the central dispatch
must publish a terminal verdict before the exact failed job is rerun. Its
dispatch job succeeded; it is not evidence of a source finding. No status is
manually promoted to success. These observations belong only to the predecessor
head and must be replaced by fresh checks and review after publication.

No production runtime, customer data, credential, retention decision, appointment
or contract has been changed. The broader #69 privacy work remains open. Next
integration work must preserve the existing identity/tenant and applicability
stacks rather than copy their source or treat this adapter fix as their successor.
