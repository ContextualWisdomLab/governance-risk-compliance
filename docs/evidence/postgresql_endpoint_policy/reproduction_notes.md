# Reproduce the endpoint contract observation

The original source is available as Git blob
`9ec92990ee67ee028ffccd7b32dbe798868a42fe` (parent56f2399, path
`cwl_grc/database.py`). The candidate is the same path in the containing
commit, blob `8ab3aa77d225e1f4a3808025706740bd74d82b23`. The regression is the
containing commit's `tests/test_postgresql_endpoint_policy.py`, blob
`8b9c73fe749bde0bf85f508fd93517c239cc319d`.

In an isolated temporary directory, copy the retained harness as
`run_endpoint_tests.py`, the two source versions as `database_before.py` and
`database_after.py`, and the regression under `tests/`. Verify their byte hashes
against the receipt before running. With the recorded local dependency versions,
run `python run_endpoint_tests.py database_before.py` (expected exit1, 17 failed
and 10 passed), followed by `python run_endpoint_tests.py database_after.py`
(expected exit0, 27 passed). Timing may differ. Each subprocess is isolated;
the harness creates no real connection and imports no incomplete application.
The test uses reserved documentation addresses and synthetic unit values only.

The ordinary repository verification is different: run the full locked Product
and the existing real PostgreSQL acceptance lane. Those import the real product;
they do not use this AST harness. The local `PGHOSTADDR`/`PGHOST`/`PGSERVICE`
cases inspect explicit arguments and are not native service-file loading tests.

The receipt also hashes the capture script and generated patch used locally.
They are diagnostic provenance, not production imports. This directory is not
an executable migration, CI replacement, access-policy bypass, published release
or a claim that the separately blocked database-diagnostic candidate was applied.
