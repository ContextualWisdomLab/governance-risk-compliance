# PostgreSQL schema-lifecycle doctoring

## Product question

How should CWL GRC migrate and operate a PostgreSQL store without letting every API replica mutate schema state, silently repair catalog damage, or accept an unreviewed driver/server/TLS profile?

## Evidence-to-decision traceability

| Evidence | Material implication | Repository decision and proof |
| --- | --- | --- |
| PostgreSQL transaction advisory locks are released with the transaction and `pg_try_advisory_xact_lock` returns immediately when the resource is already locked. | One schema owner can fail before DDL instead of waiting indefinitely or racing another deployment; the migration controller must retry after the active owner finishes. | ADR 0006; `POSTGRESQL_MIGRATION_LOCK_KEY`; real lock-contention test in `tests/test_postgresql_integration.py`. |
| PostgreSQL documents `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout`; it notes that a lock timeout at or above the statement timeout is ineffective because the statement timeout fires first. | Session waits must be finite, and the lock timeout must be strictly lower than the statement timeout. | `PostgresEngineSettings`; unit policy tests; real PostgreSQL `SHOW` assertions. |
| libpq `sslmode=verify-full` performs certificate-chain and server-hostname verification. | Remote database authentication must not rely on encryption without hostname verification. | Exact `postgresql+psycopg` driver; remote `verify-full`; explicit loopback-only CI exception. |
| SQLAlchemy `pool_pre_ping` checks connection liveness on checkout, `pool_size` bounds retained connections, and `pool_recycle` refreshes aged connections. | The pool needs explicit finite capacity and stale-connection handling; transaction loss is not hidden as success. | `pool_pre_ping=True`, finite size/overflow/acquisition/recycle settings, restart acceptance. |
| Psycopg 3.3 supports Python 3.10–3.14 and PostgreSQL 10–18; PyPI published 3.3.4 on May 1, 2026. | The Python 3.12/PostgreSQL 18 profile has a current supported DBAPI release that can be locked exactly. | `psycopg[binary]==3.3.4` and `uv.lock`. |
| PostgreSQL 18.4 was released May 14, 2026 and fixes security vulnerabilities and bugs affecting earlier 18.x versions. | The CI baseline should use the patched 18.4 release, not the original 18.0 image. | Digest-pinned `postgres:18.4-bookworm` acceptance service. |
| SQLAlchemy documents `ForeignKeyConstraint` as the table-level mechanism for composite relationships. | When tenant isolation is integrated, tenant and parent identifiers must be one relationship, not unrelated single-column keys. | ADR 0005 and the tenant-isolation stack; this PostgreSQL slice preserves compatibility with those later constraints. |

## Alternatives considered

### Application-startup migrations

Rejected for production. It allows each replica to become a writer, couples availability to DDL, and makes concurrent deployment behavior implicit. Retained only as an explicit `development` profile for local preview compatibility.

### External migration framework immediately

Deferred rather than rejected. The current schema has one released receipt and the smallest auditable change is to separate the existing versioned migration code behind one operator command and one advisory lock. Before schema complexity or multiple released upgrade paths grow, issue #8 should reassess whether Alembic or another reviewed framework better satisfies offline generation, downgrade documentation, and operational observability. Runtime ownership remains forbidden regardless of tool choice.

### `sslmode=require`

Rejected for remote production because it does not express the same hostname-verification guarantee as `verify-full`.

### Multiple supported PostgreSQL majors

Deferred. Psycopg supports a broader range, but a driver’s compatibility statement is not product acceptance. CWL GRC claims only the exact major exercised by its integration workflow. Adding another major requires a matrix lane and a release decision.

### Automatic reference-data repair

Rejected. Shared framework, control, and purpose data influences policy/evidence meaning. Runtime must surface incomplete or incompatible vocabulary rather than rewrite it during startup.

## Residual risks

- Only PostgreSQL 18.4 is exercised; no multi-major matrix exists.
- The first released migration has legacy SQLite upgrade coverage and clean PostgreSQL install coverage, but no prior PostgreSQL product release exists to upgrade from.
- Backup, point-in-time recovery, evidence-key recovery, legal hold, and declared RPO/RTO remain issue #9.
- A complete operator telemetry and readiness/drain system remains issue #11.
- The current migration implementation is repository-local, not a mature external migration framework. Future migration volume must trigger reassessment.
- The loopback CI TLS exception validates database behavior, not a production CA/hostname deployment.

## APA 7 references

PostgreSQL Global Development Group. (2025, September 25). *PostgreSQL 18 released!* https://www.postgresql.org/about/news/postgresql-18-released-3142/

PostgreSQL Global Development Group. (2026, May 14). *PostgreSQL 18.4, 17.10, 16.14, 15.18, and 14.23 released!* https://www.postgresql.org/about/news/postgresql-184-1710-1614-1518-and-1423-released-3297/

PostgreSQL Global Development Group. (2026). *Advisory lock functions* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS

PostgreSQL Global Development Group. (2026). *Client connection defaults* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/runtime-config-client.html

PostgreSQL Global Development Group. (2026). *Database connection control functions* (PostgreSQL 18 documentation). https://www.postgresql.org/docs/18/libpq-connect.html

Psycopg Team. (2026). *Installation* (Psycopg 3 documentation). https://www.psycopg.org/psycopg3/docs/basic/install.html

Python Packaging Authority. (2026, May 1). *psycopg-binary 3.3.4*. PyPI. https://pypi.org/project/psycopg-binary/3.3.4/

SQLAlchemy authors. (2026). *Connection pooling* (SQLAlchemy 2.0 documentation). https://docs.sqlalchemy.org/en/20/core/pooling.html

SQLAlchemy authors. (2026). *Defining constraints and indexes* (SQLAlchemy 2.0 documentation). https://docs.sqlalchemy.org/en/20/core/constraints.html
