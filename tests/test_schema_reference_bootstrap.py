"""RED contract that explicit migration owns shared reference-data bootstrap."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import text

from cwl_grc import create_app
from cwl_grc.database import build_engine, migrate_database


def test_runtime_never_recreates_missing_reference_data(tmp_path: Path) -> None:
    """Runtime startup checks schema but never mutates shared catalog vocabulary."""
    database_url = f"sqlite:///{tmp_path / 'reference-bootstrap.sqlite'}"
    migrate_database(database_url)
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            initial_counts = tuple(
                connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                for table_name in (
                    "control_framework",
                    "control_item",
                    "authorization_purpose",
                )
            )
            connection.execute(text("DELETE FROM control_item"))
            connection.execute(text("DELETE FROM control_framework"))
            connection.execute(text("DELETE FROM authorization_purpose"))
        assert all(count > 0 for count in initial_counts)

        create_app(
            database_url=database_url,
            evidence_key=Fernet.generate_key().decode("ascii"),
            schema_mode="runtime",
        )

        with engine.connect() as connection:
            runtime_counts = tuple(
                connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                for table_name in (
                    "control_framework",
                    "control_item",
                    "authorization_purpose",
                )
            )
        assert runtime_counts == (0, 0, 0)
    finally:
        engine.dispose()
