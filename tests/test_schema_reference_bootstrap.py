"""RED contract that explicit migration owns shared reference-data bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from cwl_grc import create_app
from cwl_grc.database import SchemaCompatibilityError, build_engine, migrate_database


def _runtime_key() -> str:
    """Return one valid ephemeral test key for persistent-runtime construction."""
    return Fernet.generate_key().decode("ascii")


def test_runtime_never_recreates_missing_reference_data(tmp_path: Path) -> None:
    """Runtime refuses missing reference data instead of mutating shared vocabulary."""
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

        with pytest.raises(SchemaCompatibilityError, match="reference data"):
            create_app(
                database_url=database_url,
                evidence_key=_runtime_key(),
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


def test_runtime_never_repairs_one_missing_official_control(tmp_path: Path) -> None:
    """A partially damaged catalog is incompatible rather than silently self-healed."""
    database_url = f"sqlite:///{tmp_path / 'partial-reference-bootstrap.sqlite'}"
    migrate_database(database_url)
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM control_item "
                    "WHERE framework_key = 'soc2_tsc_2017' "
                    "AND catalog_identifier = 'CC1.1'"
                )
            )
            remaining = connection.execute(
                text("SELECT COUNT(*) FROM control_item")
            ).scalar_one()
        assert remaining > 0

        with pytest.raises(SchemaCompatibilityError, match="reference data"):
            create_app(
                database_url=database_url,
                evidence_key=_runtime_key(),
                schema_mode="runtime",
            )

        with engine.connect() as connection:
            restored = connection.execute(
                text(
                    "SELECT COUNT(*) FROM control_item "
                    "WHERE framework_key = 'soc2_tsc_2017' "
                    "AND catalog_identifier = 'CC1.1'"
                )
            ).scalar_one()
        assert restored == 0
    finally:
        engine.dispose()
