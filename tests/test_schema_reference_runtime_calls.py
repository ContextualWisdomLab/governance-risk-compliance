"""Runtime regressions for migration-owned shared reference vocabulary."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import cwl_grc.app as app_module
from cwl_grc import create_app
from cwl_grc.database import migrate_database


def test_runtime_never_invokes_reference_seed_functions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A compatible runtime checks reference truth without entering seed code."""
    database_url = f"sqlite:///{tmp_path / 'runtime-no-seed.sqlite'}"
    migrate_database(database_url)

    def unexpected_seed(_session: object) -> None:
        """Fail if application startup enters migration-owned seed behavior."""
        pytest.fail("Runtime startup must not invoke reference-data seeding.")

    monkeypatch.setattr(app_module, "seed_control_catalog", unexpected_seed)
    monkeypatch.setattr(app_module, "seed_authorization_purposes", unexpected_seed)

    application = create_app(
        database_url=database_url,
        evidence_key=Fernet.generate_key().decode("ascii"),
        schema_mode="runtime",
    )
    assert application.state.schema_mode == "runtime"
