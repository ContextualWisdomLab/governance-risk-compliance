# Product and technical gap baseline

## Current review repairs — Proposed

Parent: PR 18 `8deede6988480a357532c28b13381705e107993a`.
CodeRabbit review5161670162 and scanner review5161669059 are current repair
inputs, not approvals. The CLI help result incorrectly mapped argparse's zero
exit to2. The repair changes only that return expression and adds17parser
contracts: original11failures/6passes, repaired17passes. Actual local timestamps,
source/test hashes and output are in
[evidence/cli_help_contract/verification_receipt.json](evidence/cli_help_contract/verification_receipt.json).
The local probe executes the actual selected main/parser definitions, not a
complete GRC import. Full locked Product remains required on the containing head.

The completed source-subset executables are retired from the current tree;
original receipts/logs remain unchanged and their historical helper references
resolve through immutable parent8deede. See the
[Proposed retirement decision](adr/proposals/verification_tool_retirement.md).
New observations must not overwrite historical evidence. Normal verification
uses actual package imports and the existing Product/PostgreSQL lanes.

On parent8deede, Product34423287766/job102703117356 passed130tests with23native
cases skipped in that environment, production983statements/244branches100%,
Ruff/docstrings/compile/lock/clean-tree successful. The separate native lane
34423287712/job102703117533 actually executed those23cases on PostgreSQL18.4.
The remaining Product warning is Starlette's httpx2 transition. These results
are retained as parent evidence, not a later commit's GREEN or release claim.

Two major review findings were reported: schema-ahead errors give inappropriate
migration guidance, and operational entrypoints can implicitly choose SQLite
and development schema ownership. Both are now causally repaired on the repair
branch: `SchemaCompatibilityError` carries a state-specific `recovery_action`
(behind/uninitialized → migration owner, ahead → compatible build or
restore/forward-fix, drift/reference/lock → their own guidance) that `cwl-grc
serve` reports, and `create_app`/officer commands require an explicit
`CWL_GRC_DATABASE_URL` and `CWL_GRC_SCHEMA_MODE` before any engine or session
side effect, with local defaults confined to `python -m cwl_grc`. Keep PR18
Draft until the exact final head passes the applicable gates. No acceptance,
exemption or operational safety claim is inferred from this bounded repair. The
blocked database diagnostic candidate remains excluded.

The following endpoint and reconciliation sections are retained history. Their
statements about which production symbols changed apply to those earlier
commits, not to the CLI help-expression repair above.

## Endpoint repair history — Proposed

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

Only `_build_postgresql_engine` changes in production in that endpoint commit.
The previously blocked DB diagnostic candidate remains excluded and unpublished.
Neither that repair nor the earlier base reconciliation changes permissions,
credentials, remote access authorization or legal applicability. Program69
remains open.

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
credential, permission, release or deployed configuration changes in that
reconciliation commit. The database diagnostic candidate previously blocked
before upload is not included. This integration is not its publication path.

## Historical requirements are preserved, not completed

The complete previous baseline is retained byte-for-byte at
[the original baseline archive](product_technical_gap_baseline_529cf321.md),
using its original blob `d03b70b89ac30a579c31d66dd1a2dc4b9e697e34`. This is the
same archive identity/path used by the separate privacy PR70. Its relative-link
base remains the docs directory. The preservation decision precedes the
reconciliation commit and is recorded in PR18 comment5610764666.

The archive's requirements and valid implementation deltas remain open unless
independently completed. Its dated PR/check observations, branch names and
readiness claims are historical, not current merge admission. Do not close or
discard identity, control/applicability, evidence-lifecycle or privacy stacks.
When PR70 and this branch are integrated, combine both current sections and
retain this identical historical artifact; do not resolve the baseline by
whole-file ours/theirs replacement.

## Historical reconciliation verification scope

The retained [execution receipt](evidence/schema_base_reconciliation/verification_receipt.json)
binds actual UTC execution instants, commands, Git blob identities, SHA-256
hashes and raw outputs. On the old workflow, the clean-tree contract passed and
the imported cancellation contract failed. Both passed on the reconciled
workflow. The combined test file compiled and retained all previous functions.

Those were two static workflow contracts executed from their test AST in a
hash-verified source subset on Python3.13.5, not full Product, PostgreSQL,
hosted Actions, actionlint, browser or deployment verification. The retired
helper is retained in immutable8deede for source inspection, not current CI use.
The unchanged normal Product/PostgreSQL commands must run on every new head;
predecessor successes do not transfer.

## Gaps and next acceptance

| Gap | Required next action |
| --- | --- |
| CLI help and observation tool lifecycle | Verify the containing head's Product/SAST and independent review; keep original receipts and historical source intact. |
| Schema recovery guidance | Repaired: per-state `recovery_action` on `SchemaCompatibilityError`; ahead no longer routes to routine migration. Next: exact-head evidence. |
| Operational configuration defaults | Repaired: explicit store/profile required before side effects; local defaults limited to `python -m cwl_grc`. Next: exact-head evidence. |
| Protected-base drift in PR18 | Preserve ordinary ancestry and re-read zero-behind state; regenerate exact-head Product/PostgreSQL/security/review evidence. |
| Dependency Review availability | Obtain authoritative dependency diff after resolving HTTP403 with canonical owner `.github` issue810. Other scanners cannot replace it. |
| CodeQL terminal evidence | Obtain exact repository/PR/base/head/language/run-bound scan and callback evidence through `.github` issue1929; dispatch success is not scan success. |
| Independent review | Resolve actual current-head findings and obtain a qualifying approval. Rate-limited/skipped bot statuses are not completed reviews. |
| Database diagnostics | The previous local candidate is unpublished. No protection of driver/server error detail, DEBUG rows or SQL literals is established here. |
| Identity and privacy source integration | Preserve PR38/descendants, PR70's HTTP safeguards and existing evidence/control/applicability stacks. Integrate through reviewed contracts. |
| Privacy lifecycle and organizational facts | Program69 remains open for applicable processing scope, rights, retention/destruction/restore, processor/transfer conditions, key custody, incidents and management evidence. |
| Release and operational readiness | Immutable release, deployed controls, restore/key recovery and authorized applicability review remain separate gates. |

The original [domain completion roadmap](product/grc-domain-completion-roadmap.md)
continues to govern product work. GRC owns compliance and control conclusions;
product owners retain their domain data, Keyverse owns identity/key-service
prerequisites, and shared CI/contracts stay with their canonical owners.
