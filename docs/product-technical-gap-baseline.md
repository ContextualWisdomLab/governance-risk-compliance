# Product and technical gap baseline

## Current endpoint repair — Proposed

Source parent: PR 18 `56f2399ea2fa97f78afcf4da73aaa67f196a58a9`.
The opt-in plaintext PostgreSQL test exception checked the URL host, while the
real SQLAlchemy dialect could select a different query host. The repair rejects
alternate query endpoint selectors in that exception and binds an explicit
numeric loopback `hostaddr` in the final driver arguments. Production
verify-full, ordinary URL ports, stored values and schema behavior remain.
`localhost` is explicitly IPv4 for the test exception; IPv6 uses `[::1]`.

The [Proposed endpoint decision](adr/proposals/postgresql_loopback_endpoint.md)
records the causal finding, alternatives, compatibility and operator guidance,
primary implementation sources and Rust replacement conditions. The
[execution receipt](evidence/postgresql_endpoint_policy/verification_receipt.json)
binds actual test instants and source/test hashes: original source 17 failures
and 10 compatibility passes; fixed source all 27 pass. These are no-network
unit contracts using actual policy definitions and dialect conversion, not
native libpq, full locked Product, PostgreSQL integration or deployed evidence.
The full current-head Product/PostgreSQL/security/review gates remain required.

Only `_build_postgresql_engine` changes in production. The previously blocked
DB diagnostic candidate remains excluded and unpublished. Neither this repair
nor the earlier base reconciliation changes permissions, credentials, remote
access authorization or legal applicability. Program 69 remains open.

The following reconciliation section describes the earlier two-parent commit
56f2399. Its no-production-change statement applies to that integration only,
not the separate endpoint repair above. All previous requirements and evidence
are retained, including the byte-identical historical archive.

## Schema-lifecycle branch reconciliation — Proposed

This section belongs to the normal integration of protected PR 68 into the
existing PR 18 schema-lifecycle branch. Its source coordinates are:

- Source parent: `ed112ed0d17e9cf81c00fba9ed3c5624146e9641`.
- Protected parent: `529cf321f134e26c0cd379ee53c06ab5297363b6`.
- Common ancestor: `83e13a1fe80cbf63fb089c337d4da749c4a7956c`.

The protected Product workflow is adopted unchanged, blob
`7b3e363082af9fc98ab0e89a1ccb59aa030ae984`. It no longer runs Product on both a
feature-branch push and its PR event, separates repository/PR concurrency, and
limits cancellation to superseded PR runs. The imported regression preserves
all previous assertions and this branch's explicit `manage_schema=True` setup.
Only its contract-specific docstring is added to the protected test.

No production module, dependency, database diagnostic setting, identity policy,
credential, permission, release or deployed configuration changes here. In
particular, the database diagnostic candidate previously blocked before upload
is not included. This integration is not an alternate publication path for it.

## Historical requirements are preserved, not completed

The complete previous baseline is retained byte-for-byte at
[the original baseline archive](product_technical_gap_baseline_529cf321.md),
using its original blob `d03b70b89ac30a579c31d66dd1a2dc4b9e697e34`. This is the
same archive identity/path used by the separate privacy PR 70. Its relative-link
base remains the docs directory. The preservation decision precedes this commit
and is recorded in PR 18 comment 5610764666.

The archive's requirements and valid implementation deltas remain open unless
independently completed. Its dated PR/check observations, branch names and
readiness claims are historical, not current merge admission. Do not close or
discard identity, control/applicability, evidence-lifecycle or privacy stacks.
When PR 70 and this branch are integrated, combine both current sections and
retain this identical historical artifact; do not resolve the baseline by
whole-file ours/theirs replacement.

## Verification scope

The retained [execution receipt](evidence/schema_base_reconciliation/verification_receipt.json)
binds actual UTC execution instants, commands, Git blob identities, SHA-256
hashes and raw outputs. On the old workflow, the clean-tree contract passed and
the imported cancellation contract failed. Both passed on the reconciled
workflow. The combined test file compiles and retains all previous functions.

These are two static workflow contracts executed from their test AST in a
hash-verified source subset on Python 3.13.5. They are not full Product,
PostgreSQL, hosted Actions, actionlint, browser or deployment verification.
Direct clone was unavailable because the execution environment could not
resolve github.com. The unchanged Product and PostgreSQL lanes must run on the
new containing commit; predecessor successes do not transfer.

## Gaps and next acceptance

| Gap | Required next action |
| --- | --- |
| Protected-base drift in PR 18 | Verify ordinary two-parent ancestry and zero behind the protected parent; regenerate exact-head Product/PostgreSQL/security/review evidence. |
| Dependency Review availability | Obtain the authoritative dependency diff after resolving the recorded HTTP 403 with canonical owner `.github` issue 810. Other scanners cannot replace it. |
| CodeQL terminal evidence | Obtain exact repository/PR/base/head/language/run-bound scan and callback evidence through `.github` issue 1929; dispatch success is not scan success. |
| Independent review | Resolve actual current-head findings and obtain a qualifying approval. Rate-limited or skipped bot statuses are not completed reviews. |
| Database diagnostics | The previous local candidate is unpublished. No protection of driver/server error detail, DEBUG rows or SQL literals is established by this merge. |
| Identity and privacy source integration | Preserve PR 38 and descendants, PR 70's HTTP safeguards and the existing evidence/control/applicability stacks. Integrate through their own reviewed contracts. |
| Privacy lifecycle and organizational facts | Program issue 69 remains open for applicable processing scope, rights, retention/destruction/restore, processor/transfer conditions, key custody, incident handling and management evidence. No compliance conclusion is made. |
| Release and operational readiness | Immutable release, deployed controls, restore/key recovery and authorized applicability review remain separate gates. |

The original [domain completion roadmap](product/grc-domain-completion-roadmap.md)
continues to govern product work. GRC owns compliance and control conclusions;
product owners retain their domain data, Keyverse owns identity/key-service
prerequisites, and shared CI/contracts stay with their canonical owners.
