"""Reject endpoint substitution in the explicit plaintext loopback test profile."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine import make_url

from cwl_grc import database as database_module


@pytest.fixture
def prepared_connections(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture real dialect arguments without creating a pool or opening a socket."""
    prepared_values: list[dict[str, Any]] = []

    def capture_engine(database_url: Any, **engine_options: Any) -> SimpleNamespace:
        """Apply SQLAlchemy's real URL conversion and final connect-argument precedence."""
        positional_args, driver_arguments = PGDialect_psycopg().create_connect_args(
            make_url(database_url)
        )
        assert not positional_args
        driver_arguments.update(engine_options["connect_args"])
        prepared_values.append(driver_arguments)
        return SimpleNamespace(driver_arguments=driver_arguments)

    monkeypatch.setattr(database_module, "create_engine", capture_engine)
    return prepared_values


def insecure_settings() -> database_module.PostgresEngineSettings:
    """Select the opt-in test exception, never the production TLS policy."""
    return database_module.PostgresEngineSettings(
        sslmode="disable", allow_insecure_loopback=True
    )


@pytest.mark.parametrize(
    "query_text",
    [
        "host=192.0.2.10",
        "host=127.0.0.1",
        "host=localhost",
        "host=127.0.0.1&host=192.0.2.10",
        "hostaddr=192.0.2.10",
        "hostaddr=127.0.0.1",
        "port=5433",
        "service=unit_profile",
        "%68ost=192.0.2.10",
    ],
)
def test_plaintext_profile_rejects_query_endpoint_selectors(
    query_text: str, prepared_connections: list[dict[str, Any]]
) -> None:
    """A loopback URL authority cannot authorize a separately selected endpoint."""
    with pytest.raises(ValueError, match="endpoint"):
        database_module.build_engine(
            f"postgresql+psycopg://unit_actor@127.0.0.1:55432/unit_store?{query_text}",
            postgres_settings=insecure_settings(),
        )
    assert prepared_connections == []


@pytest.mark.parametrize(
    ("url_host", "host_address"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("127.0.0.2", "127.0.0.2"),
        ("localhost", "127.0.0.1"),
        ("LOCALHOST", "127.0.0.1"),
        ("[::1]", "::1"),
    ],
)
def test_plaintext_profile_pins_the_validated_loopback_address(
    url_host: str, host_address: str, prepared_connections: list[dict[str, Any]]
) -> None:
    """The final driver arguments bind a numeric address, port, and disabled TLS."""
    database_module.build_engine(
        f"postgresql+psycopg://unit_actor@{url_host}:55432/unit_store?sslmode=disable",
        postgres_settings=insecure_settings(),
    )
    assert len(prepared_connections) == 1
    driver_arguments = prepared_connections[0]
    assert driver_arguments["hostaddr"] == host_address
    assert driver_arguments["host"] == url_host.strip("[]")
    assert driver_arguments["port"] == 55432
    assert driver_arguments["sslmode"] == "disable"
    assert driver_arguments["dbname"] == "unit_store"
    assert driver_arguments["user"] == "unit_actor"
    assert driver_arguments["connect_timeout"] == 5
    assert "statement_timeout=30000" in driver_arguments["options"]


@pytest.mark.parametrize(
    "query_text",
    ["host=192.0.2.10", "hostaddr=192.0.2.10", "port=55432", "service=unit_profile"],
)
def test_verified_tls_profile_preserves_existing_connection_options(
    query_text: str, prepared_connections: list[dict[str, Any]]
) -> None:
    """The repair does not ban supported option forms in the verified-TLS profile."""
    database_module.build_engine(
        f"postgresql+psycopg://unit_actor@db.example.invalid/unit_store?{query_text}"
    )
    assert len(prepared_connections) == 1
    assert prepared_connections[0]["sslmode"] == "verify-full"
    query_key, query_value = query_text.split("=", 1)
    assert str(prepared_connections[0][query_key]) == query_value


@pytest.mark.parametrize("url_host", ["192.0.2.10", "db.example.invalid", ""])
def test_plaintext_profile_still_rejects_nonloopback_authorities(
    url_host: str, prepared_connections: list[dict[str, Any]]
) -> None:
    """Additional selector checks do not replace the original local-authority gate."""
    with pytest.raises(ValueError, match="loopback"):
        database_module.build_engine(
            f"postgresql+psycopg://unit_actor@{url_host}/unit_store",
            postgres_settings=insecure_settings(),
        )
    assert prepared_connections == []


def test_plaintext_profile_still_requires_explicit_opt_in(
    prepared_connections: list[dict[str, Any]],
) -> None:
    """Loopback alone cannot turn off the production TLS default."""
    with pytest.raises(ValueError, match="loopback"):
        database_module.build_engine(
            "postgresql+psycopg://unit_actor@127.0.0.1/unit_store",
            postgres_settings=database_module.PostgresEngineSettings(sslmode="disable"),
        )
    assert prepared_connections == []


@pytest.mark.parametrize("query_text", ["sslmode=disable", "sslmode=verify-full&sslmode=disable"])
def test_verified_tls_rejects_contradictory_or_ambiguous_tls_options(
    query_text: str, prepared_connections: list[dict[str, Any]]
) -> None:
    """A query cannot downgrade or make ambiguous the selected TLS policy."""
    with pytest.raises(ValueError, match="sslmode"):
        database_module.build_engine(
            f"postgresql+psycopg://unit_actor@127.0.0.1/unit_store?{query_text}"
        )
    assert prepared_connections == []


@pytest.mark.parametrize("environment_key", ["PGHOSTADDR", "PGHOST", "PGSERVICE"])
def test_plaintext_profile_supplies_explicit_address_despite_environment_defaults(
    environment_key: str,
    monkeypatch: pytest.MonkeyPatch,
    prepared_connections: list[dict[str, Any]],
) -> None:
    """Inspect explicit arguments; this is not a native libpq or network test."""
    monkeypatch.setenv(environment_key, "192.0.2.10")
    database_module.build_engine(
        "postgresql+psycopg://unit_actor@localhost/unit_store",
        postgres_settings=insecure_settings(),
    )
    assert prepared_connections[0]["host"] == "localhost"
    assert prepared_connections[0]["hostaddr"] == "127.0.0.1"
