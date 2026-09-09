# Migration receipt timestamp: source repair and verification

Status: Proposed source repair on existing schema-lifecycle PR #18, 2026-09-10.
Parent `21c7f5169d205634d7b649078d34a92bd64230fe`; original `migrations.py`
blob `ccdfee9102c1af7c302e6107b609713953e3d016`. All existing branch changes and
lifecycle decisions remain; this is not a replacement migration implementation.

## Observed defect

The complete privacy PR #70 Product run `34413422279`, job `102672806339`,
checked out `72b1f0e4336c73fa0bcd0295a82e942bbaace5dd` and passed 183 tests with
full production coverage, but emitted 45 sqlite3 datetime-adapter deprecations.
The same raw receipt INSERT exists in this lifecycle branch. SQLAlchemy `text()`
without an explicit bind type passes a datetime to sqlite3, relying on Python's
deprecated default adapter. The warning is not proof of a privacy incident or
corrupt historical receipts; it identifies a runtime compatibility dependency.

## Causal change and invariants

Bind `applied_at` with `bindparam("applied_at", type_=DateTime())`. SQLAlchemy's
dialect now owns adaptation. Keep the existing UTC-naive TIMESTAMP convention,
receipt key, transaction ownership and early idempotency return. Do not change
DDL, rewrite stored receipts, register a process-global sqlite adapter or
suppress warnings. PostgreSQL retains its dialect-specific type handling.
SQLite textual representation may include explicit zero microseconds; the
stored time value and its precision are preserved, not a byte-format contract.

This is a two-line repair in the existing database framework adapter. It does
not introduce a new Python domain/security core or alter the product's Rust
migration target. No dependency, lock, authentication or deployment setting is
changed. There is no new API or schema version.

## RED to GREEN

`tests/test_migration_receipt.py` runs the actual `apply_schema_migrations`
function against real SQLite, using synthetic unit fixtures only. Eight cases
cover second/microsecond precision, engine-owned/caller-owned transactions and
missing/existing upgrade columns. Each applies the migration twice, checks one
unchanged receipt, UTC clock use, version-counter backfill and finalization.
DeprecationWarning is promoted to an error within the migration call, never
filtered out. All eight cases failed on the hash-verified original source with
the default datetime adapter warning; all eight passed after the explicit bind.

Executed with Python 3.13.5 and locally installed SQLAlchemy in a source-subset
workspace. Compilation and Python 3.12 grammar checks also passed. This does not
claim full-branch coverage, a Python 3.12 runtime test or PostgreSQL execution.
The existing complete Product/PostgreSQL/security/review lanes must verify the
new exact head. Do not transfer #70's full Product result to this branch.

## Integration and remaining findings

Retain Draft and existing schema-lifecycle review findings until their gates are
satisfied. The repair must reach the protected branch through normal integration
before consumers claim the deprecation removed. #70 remains unchanged and its
observed run still contains those warnings; it has not yet consumed this fix.
Its separate Starlette httpx-to-httpx2 warning requires real dependency/lock
regeneration and protocol tests, not a handwritten lock or warning filter.

## Primary references (APA 7)

Python Software Foundation. (n.d.). *sqlite3 — DB-API 2.0 interface for SQLite
 databases: Default adapters and converters (deprecated).* Retrieved September
10, 2026, from https://docs.python.org/3.13/library/sqlite3.html#default-adapters-and-converters-deprecated

SQLAlchemy authors. (n.d.). *Column elements and expressions: TextClause.bindparams.*
Retrieved September 10, 2026, from https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.TextClause.bindparams
