"""Migration receipt regressions using synthetic unit fixtures and real SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
import warnings

import pytest
from sqlalchemy import create_engine, text

from cwl_grc import migrations


@pytest.mark.parametrize("microsecond_value", [0, 456789])
@pytest.mark.parametrize("caller_transaction", [False, True])
@pytest.mark.parametrize("existing_columns", [False, True])
def test_receipt_preserves_time_without_default_adapter(
    monkeypatch: pytest.MonkeyPatch,
    microsecond_value: int,
    caller_transaction: bool,
    existing_columns: bool,
) -> None:
    """Keep upgrade, precision and idempotency without sqlite3's deprecated adapter."""
    expected_time = datetime(2026, 9, 10, 1, 2, 3, microsecond_value, tzinfo=timezone.utc)
    observed_zones: list[object] = []

    class ReceiptClock:
        """Control time without changing the real datetime object sent to the driver."""

        @staticmethod
        def now(zone_value: object) -> datetime:
            observed_zones.append(zone_value)
            return expected_time

    monkeypatch.setattr(migrations, "datetime", ReceiptClock)
    database_engine = create_engine("sqlite://")
    try:
        with database_engine.begin() as connection:
            document_columns = ", current_version_number INTEGER NOT NULL DEFAULT 0" if existing_columns else ""
            version_columns = ", is_finalized BOOLEAN" if existing_columns else ""
            connection.execute(text(
                "CREATE TABLE policy_document (policy_document_id TEXT PRIMARY KEY"
                + document_columns + ")"
            ))
            connection.execute(text(
                "CREATE TABLE policy_version (policy_document_id TEXT, version_number INTEGER"
                + version_columns + ")"
            ))
            connection.execute(text("INSERT INTO policy_document (policy_document_id) VALUES ('unit_document')"))
            connection.execute(text(
                "INSERT INTO policy_version (policy_document_id, version_number) "
                "VALUES ('unit_document', 1), ('unit_document', 2)"
            ))

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            if caller_transaction:
                with database_engine.begin() as connection:
                    migrations.apply_schema_migrations(connection)
                    migrations.apply_schema_migrations(connection)
            else:
                migrations.apply_schema_migrations(database_engine)
                migrations.apply_schema_migrations(database_engine)

        with database_engine.connect() as connection:
            receipt_rows = connection.execute(text(
                "SELECT migration_key, applied_at FROM schema_migration"
            )).all()
            assert len(receipt_rows) == 1
            assert receipt_rows[0][0] == migrations.POLICY_INTEGRITY_MIGRATION
            assert datetime.fromisoformat(receipt_rows[0][1]) == expected_time.replace(tzinfo=None)
            assert connection.execute(text(
                "SELECT current_version_number FROM policy_document"
            )).scalar_one() == 2
            assert connection.execute(text(
                "SELECT COUNT(*) FROM policy_version WHERE is_finalized = TRUE"
            )).scalar_one() == 2
        assert observed_zones == [timezone.utc]
    finally:
        database_engine.dispose()
