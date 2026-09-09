# Privacy continuation: validation response and evidence status

## Historical observation boundary (review 3973810154)

This is the preserved narrative of the earlier validation-response continuation,
not a fresh verification receipt. Reported local reading date: 2026-09-10.
For its law, T5, GitHub metadata and local-test observations, `observed_at=null`
and `raw_evidence_ref=null`: no complete raw capture with a precise collection
instant is retained alongside this narrative. Source commit, merge time and
workflow run time are not substituted for a missing observation time.
The historical facts below remain useful leads, but cannot authorize a current
PR, release, deployment or compliance decision without reacquisition.
New retained component outputs have their own [execution receipt](../evidence/privacy_header_retention/verification_receipt.json);
they do not retroactively verify this narrative.

Work parent: `7bbfbf9f4e7f9a7916852a071c65a86d7d0be9cb` on GRC PR #70.
The PR remains a source proposal, not a deployment or legal-compliance assertion.

## Changes in the earlier continuation

The FastAPI default request-validation response unnecessarily reflected
rejected values and caller-supplied dictionary keys. The new bounded 422 handler
is in the existing `cwl_grc/remote_access.py` and registered by `create_app`.
It never reads/serializes/logs validation material, retains no-store and leaves
valid payloads and existing authorization checks unchanged. See the
[Proposed decision](../adr/proposals/privacy_validation_response.md).

The source register separates source-reading reports from applicability review.
No automatic exemption or affirmative compliance decision may arise from an
unverified source. Existing protective controls stay active; unknown applicability
does not suspend the legal duty. These documentary states are not a legal engine.

## Historical baseline interpretation (CodeRabbit 3970316438)

The archived `product_technical_gap_baseline_529cf321.md` retains Git blob
`d03b70b89ac30a579c31d66dd1a2dc4b9e697e34` without editing its historical rows.
Its 2026-08-24 header is a document-generation date, not evidence that every
embedded paragraph was observed on that date. In particular, the early #32/#33
paragraphs use older source heads as “current,” while the later queue records
them as closed stack-only merges. Those paragraphs are historical claims with
**individual observation time not established**. They must not drive current
PR-state, release, or deployment decisions.

GitHub metadata reported read on 2026-09-10, without an archived raw response:

| PR | Reported state | Reported API head | Merge commit | API-reported merge time (UTC) | Target |
| --- | --- | --- | --- | --- | --- |
| #32 | closed, merged | `a86fb10cfcadd18769e5830d0982abea4e728bb5` | `7eab5bd272ca88850198f47a6c78313e3f7bd49e` | 2026-08-21T11:44:10Z | `feat/recovery-event-telemetry` |
| #33 | closed, merged | `6648cc7fc255ed6711275887ba5cd5e857073d41` | `8881d3966e3e9da29b8dce990a95295a2780618b` | 2026-08-21T11:45:58Z | `feat/internal-control-model` |

The older body/paragraph heads `c750cb8bdc347f4fc592e2e908f098520e16074f`
and `55afaee88fd0e9113a9fb655da1d2d95275c0e8c` differ from these reported API heads.
The #33-to-#32 parent relationship remains valid. A merge into either feature
branch does not establish integration into protected `develop` or deployment.
Keep all valid deltas and re-read their successor/integration evidence; do not
reopen, close or delete them merely to make a status table look consistent.

## Reported earlier verification and remaining gates

Local RED was reported as three default-validation reflection assertions, with
nine failures before the handler and ten passes after it in the expanded suite.
Combined GREEN was reported as 125 cases, 122 statements and 56 branches fully
covered in the boundary module, and ten documented symbols. The stated local
environment was Python 3.13.5 with Python 3.12 grammar checked, not a 3.12 runtime.
Six actual `create_app` route cases were added for the full locked Product lane.
These historical counts are preserved, not promoted to fresh execution evidence.

Predecessor `7bbfbf9` hosted run references for reacquisition:

| Workflow | Run | Historically reported result |
| --- | --- | --- |
| Product | 34370192978 | success |
| Security Scan | 34370193008 | success |
| SAST Semgrep | 34370192900 | success |
| CodeQL PR | 34370193003 | failure: compatibility job read `VERDICT_STATE: pending` |

The earlier report says job 102530203658 awaited a central terminal verdict,
while dispatch succeeded. This is not a source-finding assertion. No status is
manually promoted to success. Reacquire the actual head-bound logs and current
review before using any of these references for an operational decision.

No production runtime, customer data, credential, retention decision, appointment
or contract was changed in that continuation. The broader #69 work stays open.
Preserve the identity/tenant/applicability stacks rather than copy their source
or treat this adapter fix as their successor.
