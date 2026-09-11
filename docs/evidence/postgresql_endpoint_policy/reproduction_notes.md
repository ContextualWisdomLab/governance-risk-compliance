# Reproduce the endpoint contract without a second source-execution path

## Historical observation is immutable

The original local27-case observation belongs to commit
`8deede6988480a357532c28b13381705e107993a`. Its receipt and raw logs in this
directory remain byte-for-byte unchanged. Their environment, times, filenames
and tool identities describe that observation, not a new checkout or rerun.

The three purpose-complete source-subset executables have been retired from the
current tree. Their exact paths and historical blobs remain inspectable in the
[retirement decision](../../adr/proposals/verification_tool_retirement.md).
Do not overwrite `verification_receipt.json` or the original logs to record a
new run. Use a new evidence directory and actual source/environment identities.

## Normal full-checkout verification

From an authorized complete checkout of the source under review:

```sh
uv sync --locked --extra dev
uv run pytest -q tests/test_postgresql_endpoint_policy.py
uv run pytest -q tests/test_integrity_contracts.py
```

These tests import the real GRC package. They do not load extracted AST source
or substitute a package through an observation helper. The endpoint cases
still deliberately capture engine creation and inspect actual dialect
arguments without opening sockets. Native PostgreSQL acceptance remains the
separate existing workflow and its three real-database test suites.

## Original-source negative control

Use two isolated authorized worktrees, not a production checkout. The source
before the endpoint repair is `56f2399ea2fa97f78afcf4da73aaa67f196a58a9`;
the repaired source and regression are in `8deede6988480a357532c28b13381705e107993a`.
Both source revisions and tests must be reviewed before execution.

In the original-source worktree, materialize only the additive test from the
fixed revision at `tests/test_postgresql_endpoint_policy.py`, then install that
worktree's locked dependencies and run the same pytest command. Do not replace
`cwl_grc/database.py`. Original database blob:
`9ec92990ee67ee028ffccd7b32dbe798868a42fe`; fixed database blob:
`8ab3aa77d225e1f4a3808025706740bd74d82b23`; regression blob:
`8b9c73fe749bde0bf85f508fd93517c239cc319d`.

The recorded local subset had17failures/10passes before and27passes after.
A fresh full-checkout reproduction must record its own result and must not
inherit those counts or timestamps. Preserve every failure and collection
error. Running the negative control intentionally dirties its temporary test
worktree; do not relabel it a clean Product run.

The Product/PostgreSQL success recorded for8deede is historical after a new
commit. A new head requires its own locked Product, native database, security
and independent-review evidence. No source observation authorizes production
use of the plaintext exception or establishes legal compliance.
