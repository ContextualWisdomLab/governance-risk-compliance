# Avoid retaining request resources in the shared URL parser cache

Status: Proposed. Owner: GRC local HTTP adapter. Tracker: #69; existing PR #70.
Source parent: `72b1f0e4336c73fa0bcd0295a82e942bbaace5dd`.
No numeric ADR is reserved across active stacks; no protected integration,
release, deployment or legal-compliance state is implied.

## Problem and reproducible observation

A browser request can include a Referer whose path or query identifies a person,
case, document or recovery token. A hostile URL can also contain credentials in
its authority. The existing `normalized_origin` sent the entire value to
CPython's cached `urlsplit` before rejecting userinfo or comparing the origin.
Consequently those raw values remained referenced by a process-wide cache after
the request decision returned, even when the value was rejected.

Original source blob: `8895222337ec2eb4181dbc13f6fd8c027e9a13c1`.
The [retained execution receipt](../../evidence/privacy_header_retention/verification_receipt.json)
identifies the exact original and changed module/test bytes, actual execution
instants, environment, commands, exit codes and raw output digests. On the
original module 24 new assertions fail and five compatibility controls pass.
The assertions use real cache hit/miss counters, not a replacement security
function. All payloads are synthetic unit fixtures; no customer incident,
external exfiltration or remote exploit is asserted.

## Alternatives and selected change

Keep the standard URL parser but pass only the original scheme and authority.
Reject unsupported/missing schemes, userinfo, percent-encoded authority and
resource-bearing Origin before invoking it. The full bounded input is still
checked for whitespace, non-ASCII characters, backslash and fragments before
resource separation. Parse and normalize scheme/host/port as before; do not
collapse distinct origins. Referer resource text is not needed for that decision.

Rejected alternatives:
- Clearing a global cache after each request mutates other components' state and
  introduces concurrent lifetime and performance effects.
- Calling private or implementation-specific undecorated parser APIs makes the
  security adapter depend on a non-public parser interface.
- Reimplementing URL/IPv6 parsing would enlarge a narrow repair unnecessarily.
- Masking the stored evidence would not address cache retention and would damage
  authorized workflows.

The source delta remains in `cwl_grc/remote_access.py`; no consumer copies,
provider libraries, database changes or new permanent policy authority are added.
This repairs an existing Python framework adapter. The existing Rust replacement
condition remains: release and adopt a contract-equivalent owner implementation,
verify authenticated tenant/purpose boundaries and all hostile/positive cases,
then remove the legacy adapter. This is not a new Python security-core choice.

## Preserved contracts and limits

Literal local Host, exact full-origin equality, duplicate-header rejection,
proxy denial, null-Origin rejection, Fetch Metadata, intentional local JSON and
same-origin forms, validation-error privacy, no-store responses and unchanged
payload frames remain mandatory. Origin with even an empty path/query delimiter
is still rejected; Referer may include a path/query. IPv6 spelling, case and
default-port normalization keep their original behavior.

Only scheme/authority can reach this parser cache. This does not promise that
all hostnames are nonpersonal, that ASGI/server/browser/request objects never
hold a header, or that Python memory is securely zeroized. Existing processes
that already cached values require ordinary replacement/restart during a future
release; this patch does not purge their memory or authorize remote deployment.
The tests clear the cache only for test isolation, and explicitly prove that
production code does not clear an unrelated component's cached entry.

## Evidence and legal traceability

The new test file contributes 29 cases. With the unchanged earlier boundary and
validation suites, 154 component cases pass, with 127 statements and 58 branches
covered in this whole module and ten documented source symbols. Python 3.12
syntax is checked; the local runtime is Python 3.13.5 with available packages,
not a locked whole-product installation. The full Product/security/CodeQL and
independent current-head review must be reacquired after source publication.

The legal rationale is data minimization, limited retention and safeguards under
the selected Article 21/29 work packages, not a claim that those articles
mandate a specific Python parser or that this fix proves compliance. Primary
implementation citations T6-T7 are in the [source register](../../doctoring/privacy_law_sources.md).
Historical reading reports without retained raw evidence or exact timestamps
remain non-gating; no evidence clock is manufactured from a commit/date. New
component execution evidence does not retroactively validate those reports.
