# PostgreSQL schema lifecycle runbook

## Supported profile

| Component | Supported contract |
| --- | --- |
| Server | PostgreSQL 18; exact CI acceptance uses 18.4 |
| Python driver | `psycopg[binary] == 3.3.4`, hash-locked by `uv.lock` |
| SQLAlchemy dialect | `postgresql+psycopg` only |
| Remote TLS | `sslmode=verify-full` |
| CI TLS exception | `sslmode=disable` only with an explicit settings object and a loopback host |
| Transaction isolation | `READ COMMITTED` |
| Migration owner | `cwl-grc database migrate` |
| Runtime check | `cwl-grc database check` and `CWL_GRC_SCHEMA_MODE=runtime` |
| Downgrade | Not supported or claimed |

A different PostgreSQL major, driver, TLS mode, isolation level, or migration mechanism is unsupported until an ADR and exact acceptance evidence add it.

## Deployment sequence

1. **Freeze the release identity.** Record the exact source SHA, image digest when available, `uv.lock`, supported PostgreSQL version, and expected migration-key set.
2. **Back up according to the database operator’s protected recovery procedure.** This runbook does not claim backup/restore readiness; issue #9 owns that gate. Do not migrate without a recoverable database snapshot or approved point-in-time recovery boundary.
3. **Run the compatibility check.**

   ```bash
   cwl-grc database check --database-url "$CWL_GRC_DATABASE_URL"
   ```

   An uninitialized or older schema is expected to fail. An unknown future migration is an application-version mismatch; do not run an older binary against it.
4. **Run one migration owner.**

   ```bash
   cwl-grc database migrate --database-url "$CWL_GRC_DATABASE_URL"
   ```

   PostgreSQL obtains the fixed transaction-scoped advisory key before DDL. Another owner receives a bounded failure and must not retry in a tight loop.
5. **Re-run the compatibility check.** It must report `schema_compatible` and only the reviewed migration keys.
6. **Start application replicas with DDL disabled.**

   ```bash
   export CWL_GRC_SCHEMA_MODE=runtime
   cwl-grc serve
   ```

   Every replica must refuse missing tables, missing/unknown migration receipts, or incompatible catalog/purpose reference data.
7. **Observe startup and first requests.** Do not send customer traffic until database connectivity, liveness/readiness work, Keyverse/tenant authorization, and the other production gates are satisfied.

## Expand/contract rule for future migrations

The current release has one migration receipt. Future changes follow this order:

1. **Expand:** add nullable/new structures or backward-compatible behavior while the previous application remains valid.
2. **Backfill:** perform bounded, restartable, observable data movement under an explicit migration or operator job. Never hide a long backfill inside API startup.
3. **Dual-read/write only when an ADR defines it:** preserve one source of truth and explicit cutover evidence.
4. **Deploy readers of the new shape:** all runtime replicas must understand the expanded schema before destructive work.
5. **Contract:** remove old structures only in a later release after compatibility evidence proves no supported binary or rollback path requires them.

Every new migration must add clean-install and every-supported-upgrade test cases. A migration receipt is append-only; never rename, reorder, or reuse a released key.

## Failed migration

A migration failure leaves the transaction rolled back where PostgreSQL supports transactional DDL. Treat the failure as non-passing even if some external operator step succeeded.

1. Stop automated retries and preserve the exact error, application SHA, database version, migration keys, and transaction state.
2. Confirm no other migration owner holds the advisory key.
3. Run `database check`. If it reports a supported exact schema, keep application replicas on the last compatible build and investigate before retrying.
4. If it reports an older or incomplete schema, inspect the failed migration and PostgreSQL catalog without manually inserting a receipt.
5. Correct the migration on its existing reviewed branch and test clean install plus the exact failed upgrade state.
6. Re-run one migration owner after review. Never mark a failed migration complete by editing `schema_migration` directly.

## Rollback

Application rollback is permitted only when the previous binary accepts the current schema according to its own `database check`.

- If the migration was **expand-only**, deploy the previous application after its exact check passes; leave new structures in place until a reviewed contract migration.
- If the schema is **ahead** of the previous binary, do not start that binary. Restore the pre-migration recovery point or forward-fix with the current binary.
- Do not execute reverse DDL merely to imitate rollback. No downgrade path is claimed until it has explicit migrations and acceptance tests.
- Preserve immutable policy/audit history. Recovery must not overwrite or delete authoritative evidence to regain compatibility.

## Emergency read-only posture

The current product does not yet provide a complete application-level read-only deployment mode. Until that capability exists:

1. Stop mutation-capable application replicas.
2. Keep the database available only to an operator-approved, least-privilege diagnostic role or to a previously verified read-only application build.
3. Do not enable remote preview, caller-header identity, or bypassed authorization to maintain availability.
4. Capture the incident timeline, database version, schema receipts, affected tenants, and last known compatible source SHA.
5. Resume mutation traffic only after an exact compatible runtime passes database check and the incident owner approves recovery.

This posture protects integrity but is not a substitute for issue #11’s readiness, drain, telemetry, SLO, and incident controls.

## Failure classification

| Symptom | Classification | Next action |
| --- | --- | --- |
| `schema is not initialized` | No owned schema | Run one migration owner after recovery prerequisites |
| `schema is behind` | Required table/receipt absent | Deploy migration-capable current build; do not serve |
| `schema is ahead` | Older binary against future schema | Deploy a compatible binary or restore/forward-fix |
| `reference data is incomplete or incompatible` | Catalog/purpose drift or damage | Stop runtime; repair only through migration ownership |
| `advisory lock` failure | Another migration owner active | Observe the existing owner; retry only after it finishes |
| TLS/driver validation error | Unsupported connection profile | Correct URL/policy; never weaken remote TLS |
| statement/lock/pool timeout | Bounded resource contention | Preserve telemetry, remove contention/capacity cause, retry whole transaction only when safe |

## Acceptance checklist

- [ ] exact source SHA and supported PostgreSQL/driver profile recorded;
- [ ] protected recovery point available;
- [ ] one migration owner completed;
- [ ] exact migration receipts verified;
- [ ] shared framework/control/purpose identity set verified;
- [ ] runtime replicas use `schema_mode=runtime`;
- [ ] PostgreSQL Product and integration workflows pass on the unchanged head;
- [ ] SAST, Security Scan, review, and live branch policy pass;
- [ ] no claim of backup/restore, remote authorization, or production readiness exceeds current evidence.
