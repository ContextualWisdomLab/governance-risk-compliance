# ADR 0006: Separate PostgreSQL schema ownership from application runtime

## Status

Accepted for the PostgreSQL lifecycle slice.

## Context

The first GRC slice allowed `create_session_factory()` to create tables, apply custom DDL, install triggers, and seed shared reference data whenever an application process started. That behavior is convenient for a loopback developer preview, but it gives every production replica schema-writing authority, permits concurrent startup to race DDL and reference data, and cannot distinguish an uninitialized, older, or newer unsupported schema before accepting traffic.

The repository also described a PostgreSQL-ready URL without an approved DBAPI driver, a supported server matrix, real PostgreSQL acceptance tests, or bounded TLS, connection, statement, lock, idle-transaction, and pool behavior.

## Decision

1. `cwl-grc database migrate --database-url …` is the explicit schema owner. It creates the current schema, applies every supported versioned migration, installs database integrity guards, and bootstraps the exact shared control/purpose reference set.
2. `cwl-grc database check --database-url …` and application `schema_mode=runtime` are read-only compatibility paths. They do not create, upgrade, repair, or reseed schema state.
3. Runtime startup fails closed when:
   - `schema_migration` is absent;
   - required tables are missing;
   - a required migration receipt is missing;
   - an unknown future migration receipt is present; or
   - the shared framework, control-identity, or authorization-purpose set differs from the reviewed application contract.
4. PostgreSQL uses the exact `postgresql+psycopg` SQLAlchemy dialect and hash-locked `psycopg[binary]` 3.3.4 runtime.
5. The supported production server matrix for this slice is PostgreSQL 18, tested on PostgreSQL 18.4. Earlier or later majors require a separate compatibility decision and exact acceptance evidence before support is claimed.
6. Remote PostgreSQL connections use `sslmode=verify-full`. TLS may be disabled only through an explicit settings object when the host is loopback and the process is running the isolated CI acceptance lane.
7. PostgreSQL connections have finite connect, statement, lock, idle-transaction, pool-acquisition, overflow, and recycle bounds. The lock timeout is strictly lower than the statement timeout so lock contention produces the more specific failure first.
8. The migration owner obtains `pg_try_advisory_xact_lock` in the same transaction before schema DDL. A concurrent migration owner fails before changing schema state and must retry only after the existing owner finishes.
9. Product CI retains SQLite coverage. A separate exact-head PostgreSQL workflow uses a digest-pinned PostgreSQL 18.4 service and exercises clean install, DDL-free runtime startup, reference-data compatibility, advisory-lock contention, trigger parity, restart, and timeout policy.
10. Shared catalog and purpose reference data is migration-owned. Runtime never silently repairs missing or partially damaged vocabulary.

## Consequences

- Multiple application replicas can start against one compatible schema without racing DDL.
- Operators receive a deterministic next action for missing, behind, ahead, or reference-incompatible schemas.
- Existing local developer behavior remains available through the explicit `development` schema mode; production deployments select `runtime` after a successful migration job.
- The initial migration receipt remains the only released schema version. Downgrade is not supported or claimed. Future schema changes must add ordered migration receipts and clean-install plus supported-upgrade acceptance.
- Backup/restore, evidence-key recovery, retention, legal hold, release artifacts, and remote Keyverse authorization remain separate gates.

## Rejected alternatives

- **Run migrations in every API process**: rejected because replicas would share schema-writing authority and could interleave deployment work.
- **Rely on `create_all()` as a production migration system**: rejected because it cannot express reviewed upgrade ordering, compatibility windows, or rollback operations.
- **Accept any PostgreSQL driver or major version**: rejected because driver/server behavior would be unbounded and untested.
- **Use `sslmode=require`**: rejected because it does not require both trusted-CA validation and hostname verification; remote policy uses `verify-full`.
- **Automatically repair shared reference data during runtime startup**: rejected because a damaged or incompatible catalog must be visible and operator-controlled rather than silently rewritten.
- **Claim downgrade support**: rejected because no exercised backward migration exists.

## Verification

The exact-head acceptance set must prove:

- a missing schema remains untouched by runtime startup;
- explicit migration followed by runtime compatibility succeeds;
- missing tables, missing receipts, unknown future receipts, and reference-data drift fail closed;
- a concurrent PostgreSQL migration owner loses before DDL;
- PostgreSQL append-only and finalized-history guards behave like SQLite;
- PostgreSQL session timeouts and pool bounds are active;
- the process can restart and reuse the compatible schema without DDL;
- Product and PostgreSQL workflows remain exact-head, hash-locked, and clean-tree; and
- production statements, branches, and public docstrings remain 100% covered.

## References

PostgreSQL Global Development Group. (2025, September 25). *PostgreSQL 18 released!* https://www.postgresql.org/about/news/postgresql-18-released-3142/

PostgreSQL Global Development Group. (2026). *Advisory lock functions* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS

PostgreSQL Global Development Group. (2026). *Client connection defaults* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/runtime-config-client.html

PostgreSQL Global Development Group. (2026). *Database connection control functions* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/libpq-connect.html

Psycopg Team. (2026). *Installation* (Psycopg 3 documentation). https://www.psycopg.org/psycopg3/docs/basic/install.html

SQLAlchemy authors. (2026). *Connection pooling* (SQLAlchemy 2.0 documentation). https://docs.sqlalchemy.org/en/20/core/pooling.html
