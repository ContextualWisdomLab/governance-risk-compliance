# Product and technical gap baseline

## Current source repair — header-resource retention

Source parent: PR #70 `72b1f0e4336c73fa0bcd0295a82e942bbaace5dd`.
The existing local request adapter previously submitted complete Referer URLs
and rejected userinfo to CPython's process-wide URL parse cache. The repair
passes only the scheme and authority to the parser, rejecting userinfo and
resource-bearing Origin values first. It does not alter authorization, valid
payloads, database retention or the remote-preview prohibition.

The [retained execution receipt](evidence/privacy_header_retention/verification_receipt.json)
contains actual ISO 8601 UTC start/end times, raw subprocess outputs, exit codes,
source/test Git OIDs and SHA-256 digests. The original-source negative control
fails 24 cases with five positive controls passing; the unchanged 29-case set
passes after repair. Combined with the byte-identical prior component suites,
154 cases pass and the changed module has 127 statements and 58 branches fully
covered. These are local source-subset results, not full locked Product, browser,
release, deployment or organization-wide compliance evidence.

See the [Proposed cache-lifetime decision](adr/proposals/privacy_header_retention.md).
The source register and earlier continuation now identify unarchived historical
readings as non-gating. Missing observation instants and raw captures remain
null; neither midnight nor a commit timestamp is fabricated. Legal applicability,
interpretation and enacted-rule completeness remain open under #69.

The following records and the separate original archive retain valid historical
requirements and ancestry; their status words are not fresh observations.
The migration change in PR `#18`, Keyverse integration, owner-side CodeQL callbacks,
httpx2/lock migration, other lifecycle controls and organizational evidence keep
their independent gates. Nothing below supplies current-head merge admission.

## Historical continuation — 2026-09-10

PR #70 continuation source: `40af8a09785e8e77181296788eabd939c057198a`.
The non-reflecting request-validation handler is implemented in the existing
HTTP boundary; 125 component cases were reported passing with 122 statements
and 56 branches fully covered in that module. Six actual GRC route cases were
added for the full locked Product lane. No production or legal closure is claimed.

The [continuation narrative and historical interpretation](product/privacy_continuation_20260910.md)
records the two review repairs, reported #32/#33 merge metadata and predecessor
hosted runs. The preserved archive's early #32/#33 paragraphs are historical
claims with individual observation time not established, not current PR state.
Its generation date does not establish each paragraph's observation time.
The original archive blob and all valid deltas remain unchanged.

The [source register](doctoring/privacy_law_sources.md) separates source reading,
retained verification evidence and applicability review. Unarchived readings
and all organization-specific applicability decisions remain unverified.
Protective controls stay active while automatic interpretations/exemptions
remain unavailable. Current-head checks and independent review are required.
All observations below belong to the older 2026-09-09 snapshot and must not be
inherited as fresh evidence.

## Historical privacy repair snapshot — 2026-09-09

Repository: `ContextualWisdomLab/governance-risk-compliance`.
Protected source parent: `develop@529cf321f134e26c0cd379ee53c06ab5297363b6`.
Source root tree: `a80b0fda4b140affb9c3559088a7e7fd87f488da`.
Execution tracker: [GRC #69](https://github.com/ContextualWisdomLab/governance-risk-compliance/issues/69).
This change is Proposed until current-head review and protected integration;
source publication is not a deployment or legal-compliance assertion.

## Preserve the previous baseline, do not discard its valid delta

The complete preceding baseline is retained **byte-for-byte** as
[the source-parent baseline](product_technical_gap_baseline_529cf321.md), using
its existing Git blob `d03b70b89ac30a579c31d66dd1a2dc4b9e697e34`. The historical
file stays in the same directory so its relative links keep their base. Its
requirements, evidence, PR ancestry and open work are not erased or represented
as completed. Its dated PR/check observations are historical and must not be
inherited as fresh current-head evidence. This preservation decision is recorded
before the replacement current-section commit.

This current section supersedes only stale claims of *current status*, not the
prior product requirements or implementation deltas. See also the existing
[domain completion roadmap](product/grc-domain-completion-roadmap.md).

## Observed source and selected live PR state

The protected source is a local-only, unauthenticated policy/control/evidence
preview. The original request boundary used the connection peer and truthiness
of forwarding values; it did not check Host or browser Origin. Original blobs:
`app.py@26f3f760fe5e9286038251e1962a072f264a662d` and
`remote_access.py@f7eb3e8071ea02caf57cba99258233e9fcaa5a27`.

PR #38 is open and unmerged at `68da33bdf96dfbaa0488b218bc6344d5c921ceb0`, with
mechanical mergeability false in this read. Its body still describes an older
head. Treat the body as historical; do not transfer its prior GREEN claims.
The #32/#33 internal-control/applicability history is feature-branch integration,
not proof of protected deployment. Preserve the #38 identity descendants and
existing source/public-documentation stacks; this repair is not their successor
and does not authorize closing them.

## New causal repair and actual evidence

Five source-level cases reproduced the original defect by executing the fetched
original middleware: external Origin, null Origin, external Host, empty
Forwarded and an originless form all reached the downstream sentinel. That is
behavioral RED, not a real customer incident or a browser exploit claim.

The proposed fix is in `cwl_grc/remote_access.py`, registered by `create_app`.
It rejects invalid peers, authorities and browser contexts before body
consumption; preserves accepted payload bytes and response streaming; adds
non-cacheable responses; and keeps remote access disabled. A standards review
also rejected an initial no-referrer candidate because it nulls native form
Origin. A failing test preceded the same-origin referrer-policy repair.

The isolated module suite passed **115 tests**, covering **117/117 statements
and 56/56 branch destinations** of `cwl_grc/remote_access.py`; all 9 module/class/
function symbols have docstrings. Source compilation and app registration AST
checks passed. These are **component-level** results on a hash-verified source
subset using the available Python 3.13 environment, not a full locked Product
run. Existing form test files were reconstructed and verified against their
original blob hashes before adding explicit same-origin request headers. The
operator test file also replaces three fixed Fernet literals with runtime-generated
ephemeral test keys; production key custody is unchanged.
The full-product `tests/test_privacy_routes.py` adds persistence/no-mutation and
exact-value regressions; its execution remains a hosted/full-checkout gate.

Direct clone/download and locked tool acquisition were unavailable in this
execution environment. A native Chromium 144.0.7559.96 test of isolated handlers
with the actual middleware was blocked at first navigation with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`; no browser policy was bypassed. It establishes
neither browser success nor a functional regression. Browser and full-product
verification remain open, and no whole-repository coverage claim is made.

## Product and legal gaps still open

| Gap | State and next action |
| --- | --- |
| Local request authority | Implemented in proposed source; scoped tests GREEN; full locked/hosted/security/review and browser validation pending. |
| Authenticated remote GRC | Not provided by protected source. Repair/integrate existing Keyverse and tenant stacks; do not expose customer PII or treat headers as identity. |
| Internal-control/applicability integration | Preserve staged work and validate protected integration. Evidence presence remains distinct from effectiveness. |
| Privacy lifecycle and rights workflows | Not established by this protected policy/evidence slice. Implement applicable purpose, minimization, processor/transfer, retention/erasure/restore, notice/rights, incident and management workflows through their canonical owners. |
| Official rule completeness | Act 20897, Safety Measures Notice 2026-9 and enacted Act 21445 identified. Final subordinate thresholds and Notice 2026-10 clause-level effects are not fully verified; keep them unverified, not exempt or compliant. |
| Organization/deployment evidence | Actual legal entities/roles, appointments, contracts, approved notices, staffing, deployed configurations and operational evidence have not been supplied or verified. Software cannot manufacture them. |
| Release and assurance | No release/deployment/certification completion is asserted by this change. Re-read actual releases, protected checks and deployed controls before adoption. |

The detailed [privacy requirements and action register](product/privacy_obligations.md)
and [primary-law sources](doctoring/privacy_law_sources.md) are part of this
baseline. They separate legal requirements, engineering choices and unverified
applicability. September 11 changes are not the only privacy obligations;
July 1, 2027 certification commencement is separate. Incident awareness and
occurrence determine different transitional provisions.

## Owner integration and closure

GRC owns compliance decisions, not product source databases or network tooling.
Keyverse owns identity/key-service prerequisites; CO owns account/endpoint-aware
model admission and fallback; SDP owns metadata/lineage consumption; product
owners execute retention and rights; Wardnet/AppGuardrail produce operational
and source-security evidence; shared contracts and CI remain in their owners.
Use released/versioned contracts, no copied runtime or cross-service SQL.

Required path: full locked Product and security GREEN, independent exact-head
review, ordinary protected integration preserving all deltas, immutable release,
then deployed/organizational evidence and applicability review. Do not close #69
or other privacy gaps merely because this guard or its documents were merged.
