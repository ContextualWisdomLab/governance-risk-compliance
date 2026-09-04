"""Real PostgreSQL policy-history and mapping integrity acceptance tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog import FrameworkCode, get_control_item
from cwl_grc.database import (
    PostgresEngineSettings,
    build_engine,
    migrate_database,
)
from cwl_grc.models import PolicyControlMapping, PolicyVersion
from cwl_grc.policy import ControlRef, author_policy


POSTGRESQL_URL = os.environ.get("CWL_GRC_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    POSTGRESQL_URL is None,
    reason="CWL_GRC_TEST_POSTGRES_URL selects the real PostgreSQL acceptance lane.",
)


def _database_url() -> str:
    """Return the explicit integration database URL or fail the selected lane."""
    assert POSTGRESQL_URL is not None
    return POSTGRESQL_URL


def _settings() -> PostgresEngineSettings:
    """Return the explicit loopback-only PostgreSQL CI policy."""
    return PostgresEngineSettings(
        sslmode="disable",
        allow_insecure_loopback=True,
    )


def _session_factory_and_engine() -> tuple[sessionmaker[Session], Engine]:
    """Return a PostgreSQL session factory and its explicitly owned engine."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    return sessionmaker(bind=engine, expire_on_commit=False), engine


@pytest.fixture(scope="module", autouse=True)
def migrated_postgresql_schema() -> None:
    """Ensure the shared service has the exact current schema and reference truth."""
    if POSTGRESQL_URL is not None:
        migrate_database(_database_url(), postgres_settings=_settings())


def test_postgresql_finalized_policy_and_mapping_are_immutable() -> None:
    """PostgreSQL rejects finalized text, edition deletion, and mapping mutation."""
    factory, engine = _session_factory_and_engine()
    try:
        with factory() as session:
            document = author_policy(
                session,
                AuthorizationDecision(
                    "postgresql-integrity-officer",
                    PurposeCode.POLICY_AUTHORING,
                ),
                f"PostgreSQL immutable policy {datetime.now(timezone.utc).isoformat()}",
                "The finalized edition and official mappings remain immutable.",
                [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
            )
            session.commit()
            version = (
                session.query(PolicyVersion)
                .filter_by(policy_document_id=document.policy_document_id)
                .one()
            )
            mapping = (
                session.query(PolicyControlMapping)
                .filter_by(policy_version_id=version.policy_version_id)
                .one()
            )
            version_id = version.policy_version_id
            mapping_id = mapping.mapping_id

            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(
                    update(PolicyVersion)
                    .where(PolicyVersion.policy_version_id == version_id)
                    .values(policy_body="tampered PostgreSQL policy text")
                )
            session.rollback()

            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(
                    delete(PolicyControlMapping).where(
                        PolicyControlMapping.mapping_id == mapping_id
                    )
                )
            session.rollback()

            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(
                    delete(PolicyVersion).where(
                        PolicyVersion.policy_version_id == version_id
                    )
                )
            session.rollback()
    finally:
        engine.dispose()


def test_postgresql_rejects_new_mapping_on_finalized_policy_version() -> None:
    """PostgreSQL blocks a new official-control mapping after finalization."""
    factory, engine = _session_factory_and_engine()
    try:
        with factory() as session:
            document = author_policy(
                session,
                AuthorizationDecision(
                    "postgresql-mapping-officer",
                    PurposeCode.POLICY_AUTHORING,
                ),
                f"PostgreSQL mapping policy {datetime.now(timezone.utc).isoformat()}",
                "The mapped control set closes when the edition is finalized.",
                [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
            )
            session.commit()
            version = (
                session.query(PolicyVersion)
                .filter_by(policy_document_id=document.policy_document_id)
                .one()
            )
            additional_control = get_control_item(
                session,
                FrameworkCode.CSAP_2026,
                "10.2.1",
            )
            assert additional_control is not None
            session.add(
                PolicyControlMapping(
                    mapping_id=uuid4().hex,
                    policy_version_id=version.policy_version_id,
                    control_item_id=additional_control.control_item_id,
                )
            )
            with pytest.raises(DBAPIError, match="finalized"):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()
