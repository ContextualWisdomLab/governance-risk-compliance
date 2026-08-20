"""RED contracts for DDL-free runtime and exact shared reference vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

import cwl_grc.app as app_module
import cwl_grc.cli as cli_module
from cwl_grc.database import (
    SchemaCompatibilityError,
    assert_schema_compatible,
    build_engine,
    create_session_factory,
    migrate_database,
)


def _database_url(tmp_path: Path, name: str) -> str:
    """Return one isolated persistent SQLite database URL."""
    return f"sqlite:///{tmp_path / name}"


def _runtime_key() -> str:
    """Return one valid key for persistent runtime construction."""
    return Fernet.generate_key().decode("ascii")


def _forbid_reference_seed(*_args: object, **_kwargs: object) -> None:
    """Fail when a runtime path attempts migration-owned reference bootstrap."""
    pytest.fail("runtime must not invoke migration-owned reference seeders")


def test_runtime_application_never_invokes_reference_seeders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A compatible runtime app performs no catalog or purpose bootstrap calls."""
    database_url = _database_url(tmp_path, "runtime-app.sqlite")
    migrate_database(database_url)
    monkeypatch.setattr(
        app_module,
        "seed_control_catalog",
        _forbid_reference_seed,
        raising=False,
    )
    monkeypatch.setattr(
        app_module,
        "seed_authorization_purposes",
        _forbid_reference_seed,
        raising=False,
    )

    app = app_module.create_app(
        database_url=database_url,
        evidence_key=_runtime_key(),
        schema_mode="runtime",
    )

    assert app.state.schema_mode == "runtime"


def test_runtime_cli_opens_a_ddl_free_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One-shot officer commands honor runtime mode instead of owning schema work."""
    database_url = _database_url(tmp_path, "runtime-cli.sqlite")
    migrate_database(database_url)
    observed_manage_schema: list[bool] = []
    real_factory = cli_module.create_session_factory

    def capture_factory(
        url: str,
        *,
        manage_schema: bool = True,
        postgres_settings: Any = None,
    ):
        """Capture the CLI schema-ownership choice and return the real factory."""
        observed_manage_schema.append(manage_schema)
        return real_factory(
            url,
            manage_schema=manage_schema,
            postgres_settings=postgres_settings,
        )

    monkeypatch.setenv("CWL_GRC_DATABASE_URL", database_url)
    monkeypatch.setenv("CWL_GRC_SCHEMA_MODE", "runtime")
    monkeypatch.setattr(cli_module, "create_session_factory", capture_factory)
    session = cli_module._open_session()
    session.close()

    assert observed_manage_schema == [False]


def test_runtime_cli_never_invokes_reference_seeders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The officer CLI cannot repair shared vocabulary outside migration ownership."""
    database_url = _database_url(tmp_path, "runtime-cli-seed.sqlite")
    migrate_database(database_url)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", database_url)
    monkeypatch.setenv("CWL_GRC_SCHEMA_MODE", "runtime")
    monkeypatch.setattr(
        cli_module,
        "seed_control_catalog",
        _forbid_reference_seed,
        raising=False,
    )
    monkeypatch.setattr(
        cli_module,
        "seed_authorization_purposes",
        _forbid_reference_seed,
        raising=False,
    )

    session = cli_module._open_session()
    session.close()


@pytest.mark.parametrize(
    "statement",
    [
        (
            "UPDATE control_framework SET source_url = "
            "'https://attacker.invalid/catalog' "
            "WHERE framework_key = 'soc2_tsc_2017'"
        ),
        (
            "UPDATE control_item SET control_statement = 'Altered control meaning.' "
            "WHERE framework_key = 'soc2_tsc_2017' "
            "AND catalog_identifier = 'CC1.1'"
        ),
        (
            "UPDATE authorization_purpose SET purpose_description = "
            "'Altered purpose meaning.' WHERE purpose_code = 'policy_authoring'"
        ),
    ],
)
def test_runtime_rejects_reference_metadata_drift(
    tmp_path: Path,
    statement: str,
) -> None:
    """Stable identifiers cannot conceal altered framework, control, or purpose meaning."""
    database_url = _database_url(tmp_path, "reference-metadata.sqlite")
    migrate_database(database_url)
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
        with pytest.raises(SchemaCompatibilityError, match="reference data"):
            assert_schema_compatible(engine)
    finally:
        engine.dispose()


def test_runtime_cli_rejects_unknown_schema_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Officer commands never guess whether they own schema mutation."""
    database_url = _database_url(tmp_path, "invalid-mode.sqlite")
    migrate_database(database_url)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", database_url)
    monkeypatch.setenv("CWL_GRC_SCHEMA_MODE", "automatic")

    with pytest.raises(ValueError, match="schema mode"):
        cli_module._open_session()
