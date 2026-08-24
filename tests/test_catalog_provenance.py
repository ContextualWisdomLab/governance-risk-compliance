"""Realistic catalog-source, digest, import-receipt, and release workflows."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cwl_grc import create_app
from cwl_grc.app import _catalog_release_snapshot, _require_published_catalog_release
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog_provenance import (
    MAX_SOURCE_ARTIFACT_BYTES,
    publish_catalog_release,
    record_catalog_import,
    register_source_artifact,
    register_source_artifact_version,
    seed_source_license_policies,
    source_text_export_allowed,
)
from cwl_grc.database import create_session_factory
from cwl_grc.models import (
    CatalogImportRun,
    CatalogRelease,
    SourceArtifact,
    SourceArtifactVersion,
    SourceLicensePolicy,
)


_DECISION = AuthorizationDecision(
    actor_identifier="catalog-officer",
    purpose_code=PurposeCode.CATALOG_GOVERNANCE,
)
_DIGEST = hashlib.sha256(b"lawful catalog fixture").hexdigest()
_HEADERS = {
    "X-Actor-Id": "catalog-officer",
    "X-Purpose": PurposeCode.CATALOG_GOVERNANCE.value,
}


def _factory():  # noqa: ANN202
    """Return an isolated real SQLite session factory with license policies."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_source_license_policies(session)
        session.commit()
    return factory


def _artifact(session):  # noqa: ANN202
    """Register the NIST OSCAL pointer used by the fixture workflow."""
    return register_source_artifact(
        session,
        _DECISION,
        publisher_name="NIST",
        source_reference="OSCAL Control Mapping Model v1.2.3",
        source_url="https://pages.nist.gov/OSCAL-Reference/models/v1.2.3/mapping/",
        artifact_content_class="identifier_only",
        license_policy_code="identifier_only",
        allowed_source_hosts={"pages.nist.gov"},
    )


def _version(session):  # noqa: ANN202
    """Register one exact source digest for the fixture workflow."""
    artifact = _artifact(session)
    return register_source_artifact_version(
        session,
        _DECISION,
        artifact.source_artifact_id,
        edition_label="1.2.3",
        content_digest=_DIGEST,
        media_type="application/json",
        byte_length=len(b"lawful catalog fixture"),
        publication_date=date(2024, 2, 26),
        effective_date=date(2024, 2, 26),
    )


def test_license_seed_and_source_registration_are_idempotent() -> None:
    """A source pointer is allowlisted, classified, and safely repeated."""
    factory = _factory()
    with factory() as session:
        seed_source_license_policies(session)
        seed_source_license_policies(session)
        assert session.query(SourceLicensePolicy).count() == 5
        artifact = _artifact(session)
        assert _artifact(session).source_artifact_id == artifact.source_artifact_id
        assert artifact.source_host == "pages.nist.gov"
        assert source_text_export_allowed(session.get(SourceLicensePolicy, "identifier_only")) is False
        assert source_text_export_allowed(session.get(SourceLicensePolicy, "lawful_source_text")) is True
        with pytest.raises(HTTPException, match="different immutable pointer"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="OSCAL Control Mapping Model v1.2.3",
                source_url="https://csrc.nist.gov/Projects/olir",
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts={"csrc.nist.gov"},
            )
        normalized = register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference="Whitespace-normalized source",
            source_url=" https://pages.nist.gov/OSCAL/ ",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            allowed_source_hosts={"pages.nist.gov"},
        )
        assert normalized.source_url == "https://pages.nist.gov/OSCAL/"


@pytest.mark.parametrize(
    ("source_url", "hosts", "match"),
    [
        ("http://pages.nist.gov/OSCAL/", {"pages.nist.gov"}, "HTTPS"),
        ("https://evil.example/OSCAL/", {"pages.nist.gov"}, "allowlisted"),
        ("https://user:password@pages.nist.gov/OSCAL/", {"pages.nist.gov"}, "HTTPS"),
        ("https://pages.nist.gov:444/OSCAL/", {"pages.nist.gov"}, "port"),
        ("https://pages.nist.gov/OSCAL/#fragment", {"pages.nist.gov"}, "fragment"),
    ],
)
def test_source_registration_rejects_unsafe_pointers(
    source_url: str,
    hosts: set[str],
    match: str,
) -> None:
    """Source registration fails closed before any network retrieval exists."""
    factory = _factory()
    with factory() as session:
        with pytest.raises(ValueError, match=match):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="unsafe-fixture",
                source_url=source_url,
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts=hosts,
            )


def test_source_registration_accepts_explicit_default_https_port() -> None:
    """An explicit HTTPS default port remains an equivalent safe pointer."""
    factory = _factory()
    with factory() as session:
        artifact = register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference="explicit-default-port",
            source_url="https://pages.nist.gov:443/OSCAL/",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            allowed_source_hosts={"pages.nist.gov"},
        )
        assert artifact.source_host == "pages.nist.gov"
        assert artifact.source_url == "https://pages.nist.gov/OSCAL/"


def test_source_registration_collapses_equivalent_url_spellings() -> None:
    """Default ports, trailing dots, and host case register one shared artifact."""
    factory = _factory()
    with factory() as session:
        first = register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference="equivalent-pointer",
            source_url="https://PAGES.NIST.gov./OSCAL/",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            allowed_source_hosts={"pages.nist.gov"},
        )
        second = register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference="equivalent-pointer",
            source_url="https://pages.nist.gov:443/OSCAL/",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            allowed_source_hosts={"pages.nist.gov"},
        )
        assert second.source_artifact_id == first.source_artifact_id
        assert first.source_url == "https://pages.nist.gov/OSCAL/"


def test_source_registration_rejects_wrong_policy_and_purpose() -> None:
    """Unknown licenses and undeclared purposes cannot create source pointers."""
    factory = _factory()
    with factory() as session:
        with pytest.raises(HTTPException, match="license policy"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="unknown-policy",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="missing",
                allowed_source_hosts={"pages.nist.gov"},
            )
        with pytest.raises(HTTPException, match="match"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="mismatched-policy",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="lawful_source_text",
                allowed_source_hosts={"pages.nist.gov"},
            )
        with pytest.raises(HTTPException, match="catalog_governance"):
            register_source_artifact(
                session,
                AuthorizationDecision("officer", PurposeCode.EVIDENCE_BINDING),
                publisher_name="NIST",
                source_reference="wrong-purpose",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts={"pages.nist.gov"},
            )
        with pytest.raises(ValueError, match="publisher name"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name=" ",
                source_reference="blank-publisher",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts={"pages.nist.gov"},
            )
        with pytest.raises(ValueError, match="one of"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="bad-class",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="unclassified",
                license_policy_code="identifier_only",
                allowed_source_hosts={"pages.nist.gov"},
            )


@pytest.mark.parametrize(
    ("content_class", "license_policy_code"),
    [
        ("source_text", "lawful_source_text"),
        ("licensed_text", "licensed_no_redistribution"),
        ("organization_summary", "organization_summary"),
        ("translated_summary", "translated_summary"),
    ],
)
def test_source_registration_accepts_explicit_content_policy_pairs(
    content_class: str,
    license_policy_code: str,
) -> None:
    """Lawful source classifications use their explicit reviewed policy codes."""
    factory = _factory()
    with factory() as session:
        artifact = register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference=f"{content_class}-fixture",
            source_url="https://pages.nist.gov/OSCAL/",
            artifact_content_class=content_class,
            license_policy_code=license_policy_code,
            allowed_source_hosts={"pages.nist.gov"},
        )
        assert artifact.artifact_content_class == content_class
        assert artifact.license_policy_code == license_policy_code


def test_version_digest_is_idempotent_and_immutable_metadata() -> None:
    """The same digest returns one row and a metadata collision is rejected."""
    factory = _factory()
    with factory() as session:
        version = _version(session)
        repeated = _version(session)
        assert repeated.source_artifact_version_id == version.source_artifact_version_id
        with pytest.raises(HTTPException, match="different immutable metadata"):
            register_source_artifact_version(
                session,
                _DECISION,
                version.source_artifact_id,
                edition_label="1.2.3-renamed",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=version.byte_length,
            )
        for date_override in (
            {"publication_date": date(2024, 2, 27)},
            {"effective_date": date(2024, 2, 27)},
            {"withdrawal_date": date(2024, 3, 1)},
        ):
            with pytest.raises(HTTPException, match="different immutable metadata"):
                register_source_artifact_version(
                    session,
                    _DECISION,
                    version.source_artifact_id,
                    edition_label="1.2.3",
                    content_digest=_DIGEST,
                    media_type="application/json",
                    byte_length=version.byte_length,
                    **date_override,
                )
        with pytest.raises(HTTPException, match="not registered"):
            register_source_artifact_version(
                session,
                _DECISION,
                "missing-artifact",
                edition_label="1",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=1,
            )


@pytest.mark.parametrize(
    ("digest", "media_type", "byte_length", "match"),
    [
        ("bad", "application/json", 1, "digest"),
        (_DIGEST, "application/pdf", 1, "media type"),
        (_DIGEST, "application/json", 0, "between"),
        (_DIGEST, "application/json", MAX_SOURCE_ARTIFACT_BYTES + 1, "between"),
    ],
)
def test_version_registration_validates_digest_media_and_size(
    digest: str,
    media_type: str,
    byte_length: int,
    match: str,
) -> None:
    """Mutable, active, or oversized source inputs are rejected before persistence."""
    factory = _factory()
    with factory() as session:
        artifact = _artifact(session)
        with pytest.raises(ValueError, match=match):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1",
                content_digest=digest,
                media_type=media_type,
                byte_length=byte_length,
            )


def test_version_registration_validates_period_and_integer_type() -> None:
    """Temporal and size metadata cannot describe an impossible artifact."""
    factory = _factory()
    with factory() as session:
        artifact = _artifact(session)
        with pytest.raises(ValueError, match="publication"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=1,
                publication_date=date(2024, 2, 27),
                effective_date=date(2024, 2, 26),
            )
        with pytest.raises(ValueError, match="effective"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=1,
                effective_date=date(2024, 2, 27),
                withdrawal_date=date(2024, 2, 26),
            )
        with pytest.raises(ValueError, match="publication"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=1,
                publication_date=date(2024, 2, 27),
                withdrawal_date=date(2024, 2, 26),
            )
        with pytest.raises(ValueError, match="integer"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=True,
            )


def test_source_and_version_race_recovery_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent unique creation returns the winner or preserves the original error."""
    factory = _factory()
    with factory() as session:
        source_winner = SourceArtifact(
            source_artifact_id="winner-source",
            publisher_name="NIST",
            source_reference="race-source",
            source_url="https://pages.nist.gov/OSCAL/",
            source_host="pages.nist.gov",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            created_at=datetime(2024, 1, 1),
        )
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def source_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def source_query(entity):  # noqa: ANN001
            if entity is SourceArtifact and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: source_winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", source_flush)
        monkeypatch.setattr(session, "query", source_query)
        assert register_source_artifact(
            session,
            _DECISION,
            publisher_name="NIST",
            source_reference="race-source",
            source_url="https://pages.nist.gov/OSCAL/",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            allowed_source_hosts={"pages.nist.gov"},
        ) is source_winner

    factory = _factory()
    with factory() as session:
        source_winner = SourceArtifact(
            source_artifact_id="conflicting-source",
            publisher_name="NIST",
            source_reference="race-conflict",
            source_url="https://pages.nist.gov/other/",
            source_host="pages.nist.gov",
            artifact_content_class="identifier_only",
            license_policy_code="identifier_only",
            created_at=datetime(2024, 1, 1),
        )
        race = {"flushed": False}
        session.autoflush = False
        original_query = session.query

        def source_conflict_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        monkeypatch.setattr(session, "flush", source_conflict_flush)
        monkeypatch.setattr(
            session,
            "query",
            lambda entity: (
                SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: source_winner)
                )
                if entity is SourceArtifact and race["flushed"]
                else original_query(entity)
            ),
        )
        with pytest.raises(HTTPException, match="different immutable pointer"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="race-conflict",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts={"pages.nist.gov"},
            )

    factory = _factory()
    with factory() as session:
        race = {"flushed": False}
        session.autoflush = False

        def source_flush_without_winner(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        monkeypatch.setattr(session, "flush", source_flush_without_winner)
        with pytest.raises(IntegrityError, match="race"):
            register_source_artifact(
                session,
                _DECISION,
                publisher_name="NIST",
                source_reference="no-winner",
                source_url="https://pages.nist.gov/OSCAL/",
                artifact_content_class="identifier_only",
                license_policy_code="identifier_only",
                allowed_source_hosts={"pages.nist.gov"},
            )


def test_version_race_recovery_returns_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent version insert resolves to the existing digest row."""
    factory = _factory()
    with factory() as session:
        artifact = _artifact(session)
        winner = SourceArtifactVersion(
            source_artifact_version_id="winner-version",
            source_artifact_id=artifact.source_artifact_id,
            edition_label="1.2.3",
            content_digest=_DIGEST,
            media_type="application/json",
            byte_length=22,
            version_status="registered",
            registered_at=datetime.now(),
        )
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def version_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def version_query(entity):  # noqa: ANN001
            if entity is SourceArtifactVersion and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", version_flush)
        monkeypatch.setattr(session, "query", version_query)
        assert register_source_artifact_version(
            session,
            _DECISION,
            artifact.source_artifact_id,
            edition_label="1.2.3",
            content_digest=_DIGEST,
            media_type="application/json",
            byte_length=22,
        ) is winner

    factory = _factory()
    with factory() as session:
        artifact = _artifact(session)
        winner = SourceArtifactVersion(
            source_artifact_version_id="conflicting-version",
            source_artifact_id=artifact.source_artifact_id,
            edition_label="different-edition",
            content_digest=_DIGEST,
            media_type="application/json",
            byte_length=22,
            version_status="registered",
            registered_at=datetime.now(),
        )
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def version_conflict_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def version_conflict_query(entity):  # noqa: ANN001
            if entity is SourceArtifactVersion and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", version_conflict_flush)
        monkeypatch.setattr(session, "query", version_conflict_query)
        with pytest.raises(HTTPException, match="different immutable metadata"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1.2.3",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=22,
            )

    factory = _factory()
    with factory() as session:
        artifact = _artifact(session)
        session.autoflush = False

        def version_flush_without_winner(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            raise IntegrityError("race", {}, RuntimeError("race"))

        monkeypatch.setattr(session, "flush", version_flush_without_winner)
        with pytest.raises(IntegrityError, match="race"):
            register_source_artifact_version(
                session,
                _DECISION,
                artifact.source_artifact_id,
                edition_label="1.2.3",
                content_digest=_DIGEST,
                media_type="application/json",
                byte_length=22,
            )


def test_import_missing_version_and_receipt_conflicts() -> None:
    """Import identity requires a registered version and a complete receipt."""
    factory = _factory()
    with factory() as session:
        with pytest.raises(HTTPException, match="version is not registered"):
            record_catalog_import(
                session,
                _DECISION,
                "missing-version",
                parser_version="parser",
                importer_commit="e" * 40,
                run_status="succeeded",
            )
        version = _version(session)
        session.add(
            CatalogImportRun(
                catalog_import_run_id="run-without-receipt",
                source_artifact_version_id=version.source_artifact_version_id,
                parser_version="parser-without-receipt",
                importer_commit="e" * 40,
                run_status="succeeded",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
        )
        session.commit()
        with pytest.raises(HTTPException, match="no receipt"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="parser-without-receipt",
                importer_commit="e" * 40,
                run_status="succeeded",
            )
        with pytest.raises(ValueError, match="cannot carry"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="parser-with-failure",
                importer_commit="e" * 40,
                run_status="succeeded",
                failure_code="not-allowed",
            )


def test_import_race_recovery_returns_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent parser receipt resolves to the durable winner."""
    factory = _factory()
    with factory() as session:
        version = _version(session)
        receipt = SimpleNamespace(catalog_import_receipt_id="winner-receipt")
        winner = SimpleNamespace(
            run_status="succeeded",
            importer_commit="f" * 40,
            failure_code=None,
            receipt=SimpleNamespace(
                catalog_import_receipt_id=receipt.catalog_import_receipt_id,
                requirement_count=0,
                changed_requirement_count=0,
                warning_count=0,
            ),
            catalog_import_run_id="winner-run",
        )
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def import_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def import_query(entity):  # noqa: ANN001
            if entity is CatalogImportRun and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", import_flush)
        monkeypatch.setattr(session, "query", import_query)
        result = record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="race-parser",
            importer_commit="f" * 40,
            run_status="succeeded",
        )
        assert result.created is False
        assert result.run is winner

    factory = _factory()
    with factory() as session:
        version = _version(session)
        winner = SimpleNamespace(
            run_status="succeeded",
            importer_commit="different-commit",
            failure_code=None,
            receipt=SimpleNamespace(
                catalog_import_receipt_id="conflicting-receipt",
                requirement_count=0,
                changed_requirement_count=0,
                warning_count=0,
            ),
            catalog_import_run_id="conflicting-run",
        )
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def import_conflict_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def import_conflict_query(entity):  # noqa: ANN001
            if entity is CatalogImportRun and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", import_conflict_flush)
        monkeypatch.setattr(session, "query", import_conflict_query)
        with pytest.raises(HTTPException, match="immutable parser receipt"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="conflict-parser",
                importer_commit="f" * 40,
                run_status="succeeded",
            )

    factory = _factory()
    with factory() as session:
        version = _version(session)
        race = {"flushed": False}
        session.autoflush = False

        def import_flush_without_winner(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        monkeypatch.setattr(session, "flush", import_flush_without_winner)
        with pytest.raises(IntegrityError, match="race"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="no-winner",
                importer_commit="f" * 40,
                run_status="succeeded",
            )


def test_release_missing_version_and_race_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Release publication fails closed for missing versions and handles a unique race."""
    factory = _factory()
    with factory() as session:
        with pytest.raises(HTTPException, match="version is not registered"):
            publish_catalog_release(session, _DECISION, "missing-version", release_key="release")
        version = _version(session)
        record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="release-parser",
            importer_commit="g" * 40,
            run_status="succeeded",
        )
        winner = SimpleNamespace(catalog_release_id="winner-release")
        original_query = session.query
        race = {"flushed": False}
        session.autoflush = False

        def release_flush(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        def release_query(entity):  # noqa: ANN001
            if entity is CatalogRelease and race["flushed"]:
                return SimpleNamespace(
                    filter_by=lambda **_kwargs: SimpleNamespace(one_or_none=lambda: winner)
                )
            return original_query(entity)

        monkeypatch.setattr(session, "flush", release_flush)
        monkeypatch.setattr(session, "query", release_query)
        assert publish_catalog_release(
            session,
            _DECISION,
            version.source_artifact_version_id,
            release_key="race-release",
        ) is winner

    factory = _factory()
    with factory() as session:
        version = _version(session)
        record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="release-parser",
            importer_commit="g" * 40,
            run_status="succeeded",
        )
        race = {"flushed": False}
        session.autoflush = False

        def release_flush_without_winner(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            race["flushed"] = True
            raise IntegrityError("race", {}, RuntimeError("race"))

        monkeypatch.setattr(session, "flush", release_flush_without_winner)
        with pytest.raises(IntegrityError, match="race"):
            publish_catalog_release(
                session,
                _DECISION,
                version.source_artifact_version_id,
                release_key="no-winner-release",
            )


def test_import_receipt_release_and_append_only_guards() -> None:
    """A successful import can publish once and every historical row is immutable."""
    factory = _factory()
    with factory() as session:
        version = _version(session)
        with pytest.raises(HTTPException, match="successful import"):
            publish_catalog_release(
                session,
                _DECISION,
                version.source_artifact_version_id,
                release_key="oscal-1.2.3",
            )
        result = record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="oscal-json-1",
            importer_commit="a" * 40,
            run_status="succeeded",
            requirement_count=12,
            changed_requirement_count=2,
            warning_count=1,
        )
        repeated = record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="oscal-json-1",
            importer_commit="a" * 40,
            run_status="succeeded",
            requirement_count=12,
            changed_requirement_count=2,
            warning_count=1,
        )
        assert result.created is True
        assert repeated.created is False
        assert repeated.receipt.receipt_digest == result.receipt.receipt_digest
        release = publish_catalog_release(
            session,
            _DECISION,
            version.source_artifact_version_id,
            release_key="oscal-1.2.3",
        )
        assert publish_catalog_release(
            session,
            _DECISION,
            version.source_artifact_version_id,
            release_key="oscal-1.2.3",
        ).catalog_release_id == release.catalog_release_id
        second_version = register_source_artifact_version(
            session,
            _DECISION,
            version.source_artifact.source_artifact_id,
            edition_label="1.2.4",
            content_digest=hashlib.sha256(b"second catalog fixture").hexdigest(),
            media_type="application/json",
            byte_length=len(b"second catalog fixture"),
        )
        with pytest.raises(IntegrityError, match="version mismatch"):
            session.execute(
                text(
                    "INSERT INTO catalog_release ("
                    "catalog_release_id, source_artifact_version_id, catalog_import_run_id, "
                    "release_key, release_status, created_at) VALUES ("
                    ":release_id, :version_id, :run_id, :release_key, 'published', CURRENT_TIMESTAMP)"
                ),
                {
                    "release_id": "mismatched-release",
                    "version_id": second_version.source_artifact_version_id,
                    "run_id": result.run.catalog_import_run_id,
                    "release_key": "mismatched",
                },
            )
        session.rollback()
        for table, identifier_column, identifier in (
            ("source_artifact_version", "source_artifact_version_id", version.source_artifact_version_id),
            ("catalog_import_run", "catalog_import_run_id", result.run.catalog_import_run_id),
            ("catalog_import_receipt", "catalog_import_receipt_id", result.receipt.catalog_import_receipt_id),
            ("catalog_release", "catalog_release_id", release.catalog_release_id),
        ):
            with pytest.raises(IntegrityError):
                session.execute(
                    text(f"UPDATE {table} SET {identifier_column} = :new_id WHERE {identifier_column} = :id"),
                    {"new_id": f"changed-{identifier}", "id": identifier},
                )
            session.rollback()
            with pytest.raises(IntegrityError):
                session.execute(
                    text(f"DELETE FROM {table} WHERE {identifier_column} = :id"),
                    {"id": identifier},
                )
            session.rollback()


def test_import_failures_and_conflicts_are_explicit() -> None:
    """Failed runs require a reason and an immutable key cannot be rewritten."""
    factory = _factory()
    with factory() as session:
        version = _version(session)
        with pytest.raises(ValueError, match="failure code"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="oscal-json-1",
                importer_commit="b" * 40,
                run_status="failed",
            )
        with pytest.raises(ValueError, match="non-negative"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="oscal-json-1",
                importer_commit="b" * 40,
                run_status="succeeded",
                requirement_count=-1,
            )
        failed = record_catalog_import(
            session,
            _DECISION,
            version.source_artifact_version_id,
            parser_version="oscal-json-1",
            importer_commit="b" * 40,
            run_status="failed",
            failure_code="invalid_oscal",
        )
        with pytest.raises(HTTPException, match="immutable parser receipt"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="oscal-json-1",
                importer_commit="c" * 40,
                run_status="failed",
                failure_code="different_failure",
            )
        with pytest.raises(HTTPException, match="immutable parser receipt"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="oscal-json-1",
                importer_commit="b" * 40,
                run_status="succeeded",
            )
        with pytest.raises(HTTPException, match="immutable parser receipt"):
            record_catalog_import(
                session,
                _DECISION,
                version.source_artifact_version_id,
                parser_version="oscal-json-1",
                importer_commit="b" * 40,
                run_status="failed",
                requirement_count=1,
                failure_code="different_failure",
            )
        assert failed.run.run_status == "failed"


def test_catalog_routes_execute_the_local_governance_workflow() -> None:
    """The loopback HTTP surface exposes source, digest, receipt, and release actions."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    artifact_response = client.post(
        "/catalog/source-artifacts",
        headers=_HEADERS,
        json={
            "publisher_name": "NIST",
            "source_reference": "OSCAL Mapping v1.2.3",
            "source_url": "https://pages.nist.gov/OSCAL-Reference/models/v1.2.3/mapping/",
            "artifact_content_class": "identifier_only",
            "license_policy_code": "identifier_only",
            "allowed_source_hosts": ["pages.nist.gov"],
        },
    )
    assert artifact_response.status_code == 201
    artifact_id = artifact_response.json()["source_artifact_id"]
    version_response = client.post(
        f"/catalog/source-artifacts/{artifact_id}/versions",
        headers=_HEADERS,
        json={
            "edition_label": "1.2.3",
            "content_digest": _DIGEST,
            "media_type": "application/json",
            "byte_length": 22,
            "publication_date": "2024-02-26",
        },
    )
    assert version_response.status_code == 201
    version_id = version_response.json()["source_artifact_version_id"]
    import_response = client.post(
        "/catalog/import-runs",
        headers=_HEADERS,
        json={
            "source_artifact_version_id": version_id,
            "parser_version": "oscal-json-1",
            "importer_commit": "d" * 40,
            "run_status": "succeeded",
            "requirement_count": 1,
        },
    )
    assert import_response.status_code == 201
    release_response = client.post(
        "/catalog/releases",
        headers=_HEADERS,
        json={
            "source_artifact_version_id": version_id,
            "release_key": "oscal-1.2.3",
        },
    )
    assert release_response.status_code == 201
    assert release_response.json()["release_status"] == "published"
    releases_response = client.get(
        "/catalog/releases",
        headers=_HEADERS,
        params={"limit": 1},
    )
    assert releases_response.status_code == 200
    assert releases_response.json()["releases"][0]["catalog_release_id"] == release_response.json()["catalog_release_id"]
    assert releases_response.json()["limit"] == 1
    assert releases_response.json()["offset"] == 0
    assert releases_response.json()["has_more"] is False
    assert releases_response.json()["next_action"].startswith("Review the release")
    detail_response = client.get(
        f"/catalog/releases/{release_response.json()['catalog_release_id']}",
        headers=_HEADERS,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["release"]["content_digest"] == _DIGEST
    assert detail_response.json()["release"]["artifact_content_class"] == "identifier_only"
    assert detail_response.json()["release"]["source_text_export_allowed"] is False
    assert detail_response.json()["release"]["identifier_export_allowed"] is True
    assert detail_response.json()["next_action"].startswith("Review the provenance")
    second_digest = hashlib.sha256(b"next lawful catalog fixture").hexdigest()
    second_version_response = client.post(
        f"/catalog/source-artifacts/{artifact_id}/versions",
        headers=_HEADERS,
        json={
            "edition_label": "1.2.4",
            "content_digest": second_digest,
            "media_type": "application/json",
            "byte_length": 28,
            "publication_date": "2024-03-01",
        },
    )
    assert second_version_response.status_code == 201
    second_version_id = second_version_response.json()["source_artifact_version_id"]
    assert client.post(
        "/catalog/import-runs",
        headers=_HEADERS,
        json={
            "source_artifact_version_id": second_version_id,
            "parser_version": "oscal-json-2",
            "importer_commit": "e" * 40,
            "run_status": "succeeded",
            "requirement_count": 2,
            "changed_requirement_count": 1,
        },
    ).status_code == 201
    second_release_response = client.post(
        "/catalog/releases",
        headers=_HEADERS,
        json={
            "source_artifact_version_id": second_version_id,
            "release_key": "oscal-1.2.4",
        },
    )
    assert second_release_response.status_code == 201
    first_release_id = release_response.json()["catalog_release_id"]
    second_release_id = second_release_response.json()["catalog_release_id"]
    first_page = client.get(
        "/catalog/releases",
        headers=_HEADERS,
        params={"limit": 1},
    )
    assert first_page.status_code == 200
    assert len(first_page.json()["releases"]) == 1
    assert first_page.json()["has_more"] is True
    second_page = client.get(
        "/catalog/releases",
        headers=_HEADERS,
        params={"limit": 1, "offset": 1},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["releases"]) == 1
    assert second_page.json()["has_more"] is False
    assert client.get(
        "/catalog/releases",
        headers=_HEADERS,
        params={"limit": 0},
    ).status_code == 422
    assert client.get(
        "/catalog/releases",
        headers=_HEADERS,
        params={"offset": 100_001},
    ).status_code == 422
    assert client.get(
        "/catalog/releases/missing",
        headers=_HEADERS,
    ).status_code == 404
    assert client.get(
        f"/catalog/releases/{first_release_id}",
    ).status_code == 401
    comparison_response = client.get(
        f"/catalog/releases/{first_release_id}/compare/{second_release_id}",
        headers=_HEADERS,
    )
    assert comparison_response.status_code == 200
    comparison = comparison_response.json()
    assert comparison["comparison_scope"] == "source_metadata_and_import_receipt"
    assert "content_digest" in comparison["changed_fields"]
    assert "publisher_name" in comparison["unchanged_fields"]
    assert comparison["limitations"]
    assert comparison["next_action"].startswith("Review the changed")
    assert client.get(
        f"/catalog/releases/{first_release_id}/compare/{second_release_id}"
    ).status_code == 401
    assert client.get(
        f"/catalog/releases/missing/compare/{second_release_id}",
        headers=_HEADERS,
    ).status_code == 404
    assert client.get(
        f"/catalog/releases/{first_release_id}/compare/missing",
        headers=_HEADERS,
    ).status_code == 404
    assert client.get("/catalog/releases").status_code == 401
    assert client.post(
        "/catalog/source-artifacts",
        json={
            "publisher_name": "NIST",
            "source_reference": "missing-purpose",
            "source_url": "https://pages.nist.gov/OSCAL/",
            "artifact_content_class": "identifier_only",
            "license_policy_code": "identifier_only",
            "allowed_source_hosts": ["pages.nist.gov"],
        },
    ).status_code == 401
    assert client.post(
        "/catalog/source-artifacts",
        headers=_HEADERS,
        json={
            "publisher_name": "NIST",
            "source_reference": "caller-controlled-host-list",
            "source_url": "https://evil.example/OSCAL/",
            "artifact_content_class": "identifier_only",
            "license_policy_code": "identifier_only",
            "allowed_source_hosts": ["evil.example"],
        },
    ).status_code == 422
    assert client.post(
        "/catalog/source-artifacts",
        headers=_HEADERS,
        json={
            "publisher_name": "",
            "source_reference": "bad-value",
            "source_url": "https://pages.nist.gov/OSCAL/",
            "artifact_content_class": "identifier_only",
            "license_policy_code": "identifier_only",
            "allowed_source_hosts": ["pages.nist.gov"],
        },
    ).status_code == 422
    assert client.post(
        f"/catalog/source-artifacts/{artifact_id}/versions",
        headers=_HEADERS,
        json={
            "edition_label": "bad-type",
            "content_digest": _DIGEST,
            "media_type": "application/json",
            "byte_length": 1,
            "publication_date": 2024,
        },
    ).status_code == 400
    assert client.post(
        f"/catalog/source-artifacts/{artifact_id}/versions",
        headers=_HEADERS,
        json={
            "edition_label": "bad-digest",
            "content_digest": "bad",
            "media_type": "application/json",
            "byte_length": 1,
        },
    ).status_code == 422
    assert client.post(
        "/catalog/import-runs",
        headers=_HEADERS,
        json={"source_artifact_version_id": "missing", "run_status": "bad"},
    ).status_code == 404
    assert client.post(
        "/catalog/import-runs",
        headers=_HEADERS,
        json={
            "source_artifact_version_id": version_id,
            "parser_version": "bad-status",
            "importer_commit": "h" * 40,
            "run_status": "succeeded",
            "failure_code": "invalid",
        },
    ).status_code == 422
    assert client.post(
        "/catalog/releases",
        headers=_HEADERS,
        json={"source_artifact_version_id": "missing", "release_key": "missing"},
    ).status_code == 404
    assert client.post(
        "/catalog/releases",
        headers=_HEADERS,
        json={"source_artifact_version_id": version_id, "release_key": " "},
    ).status_code == 422
    assert client.post(
        f"/catalog/source-artifacts/{artifact_id}/versions",
        headers=_HEADERS,
        json={
            "edition_label": "bad",
            "content_digest": "bad",
            "media_type": "application/json",
            "byte_length": 1,
            "publication_date": "not-a-date",
        },
    ).status_code == 400


def test_release_snapshot_rejects_unlinked_import_receipt() -> None:
    """A legacy release without a durable import link fails closed."""
    release = SimpleNamespace(
        source_artifact_version=SimpleNamespace(source_artifact=SimpleNamespace()),
        catalog_import_run=None,
    )
    with pytest.raises(HTTPException, match="immutable successful import receipt"):
        _catalog_release_snapshot(release)


def test_release_snapshot_rejects_mismatched_import_version() -> None:
    """A release snapshot cannot combine metadata from different source versions."""
    release = SimpleNamespace(
        source_artifact_version=SimpleNamespace(
            source_artifact_version_id="version-a",
            source_artifact=SimpleNamespace(),
        ),
        catalog_import_run=SimpleNamespace(
            source_artifact_version_id="version-b",
            run_status="succeeded",
            receipt=SimpleNamespace(),
        ),
    )
    with pytest.raises(HTTPException, match="different source version"):
        _catalog_release_snapshot(release)


def test_catalog_comparison_rejects_unpublished_release() -> None:
    """Release comparisons remain limited to published catalog identities."""
    published = SimpleNamespace(release_status="published")
    _require_published_catalog_release(published, "first")
    with pytest.raises(HTTPException, match="second catalog release is not published"):
        _require_published_catalog_release(SimpleNamespace(release_status="withdrawn"), "second")
