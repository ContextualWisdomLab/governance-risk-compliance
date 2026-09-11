"""Operational entrypoints must require an explicit store and schema profile."""

from __future__ import annotations

from pathlib import Path

import pytest

import cwl_grc.__main__ as main_module
import cwl_grc.cli as cli_module
from cwl_grc import create_app


@pytest.fixture(autouse=True)
def clear_operational_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove every database/profile setting so only explicit values remain."""
    monkeypatch.delenv("CWL_GRC_DATABASE_URL", raising=False)
    monkeypatch.delenv("CWL_GRC_SCHEMA_MODE", raising=False)


def test_create_app_requires_an_explicit_store() -> None:
    """A missing database setting fails before any local SQLite file is created."""
    with pytest.raises(ValueError, match="CWL_GRC_DATABASE_URL"):
        create_app(evidence_key=None)


def test_create_app_requires_an_explicit_schema_profile(tmp_path: Path) -> None:
    """A missing profile fails before an engine or schema mutation is started."""
    database_url = f"sqlite:///{tmp_path / 'profile-required.sqlite'}"
    with pytest.raises(ValueError, match="CWL_GRC_SCHEMA_MODE"):
        create_app(database_url=database_url, evidence_key=None)
    assert not (tmp_path / "profile-required.sqlite").exists()


def test_open_session_requires_an_explicit_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Officer commands never pick an implicit local store before building a session."""
    monkeypatch.setattr(
        cli_module,
        "create_session_factory",
        lambda *args, **kwargs: pytest.fail("session factory built without a store"),
    )
    with pytest.raises(ValueError, match="CWL_GRC_DATABASE_URL"):
        cli_module._open_session()


def test_open_session_requires_an_explicit_schema_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Officer commands never infer schema ownership from a database URL alone."""
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", "sqlite://")
    monkeypatch.setattr(
        cli_module,
        "create_session_factory",
        lambda *args, **kwargs: pytest.fail("session factory built without a profile"),
    )
    with pytest.raises(ValueError, match="CWL_GRC_SCHEMA_MODE"):
        cli_module._open_session()


def test_module_entrypoint_supplies_local_development_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ``python -m cwl_grc`` selects the local SQLite development profile."""
    captured: dict[str, object] = {}

    def fake_run(application: object, host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        main_module,
        "create_app",
        lambda *, database_url, schema_mode: captured.update(
            {"database_url": database_url, "schema_mode": schema_mode}
        ),
    )

    main_module.main()

    assert captured["database_url"] == "sqlite:///grc_product.sqlite"
    assert captured["schema_mode"] == "development"
    assert captured["host"] == "127.0.0.1"
