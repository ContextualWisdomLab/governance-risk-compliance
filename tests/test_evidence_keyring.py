"""Evidence key inventory, rotation, context, and rewrap contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

import cwl_grc.encryption as encryption_module
from cwl_grc import create_app
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import (
    EVIDENCE_ALGORITHM_VERSION,
    LEGACY_EVIDENCE_ALGORITHM_VERSION,
    EncryptedEvidence,
    EvidenceCipher,
    EvidenceDecryptionError,
    EvidenceKeyring,
    make_evidence_context,
)
from cwl_grc.evidence import (
    create_evidence_record,
    record_encryption_envelope,
    rewrap_evidence_records,
)
from cwl_grc.migrations import apply_schema_migrations
from cwl_grc.models import EvidenceRecord


TENANT_ID = "tenant-a"
RECORD_ID = "evidence-1"
CONTEXT = make_evidence_context(TENANT_ID, RECORD_ID)


def _key() -> bytes:
    """Return one generated Fernet key for an isolated test inventory."""
    return Fernet.generate_key()


def _rotating_cipher(active_key_id: str = "key-2026-08") -> EvidenceCipher:
    """Return a ring with one active key and one approved predecessor."""
    return EvidenceCipher(
        None,
        keyring=EvidenceKeyring(
            {
                "key-2026-07": _key(),
                active_key_id: _key(),
            },
            active_key_id=active_key_id,
        ),
    )


def _seeded_factory():  # noqa: ANN202
    """Return an isolated store with the shared catalog and purpose vocabulary."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()
    return factory


def _invalid_envelope(
    cipher: EvidenceCipher,
    payload: object,
    *,
    context_digest: str,
    source_content_digest: str,
) -> EncryptedEvidence:
    """Build a cryptographically valid envelope containing an invalid JSON payload shape."""
    raw = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    ciphertext = cipher._keyring._fernet_for(cipher.active_key_id).encrypt(raw)
    envelope = EncryptedEvidence(
        ciphertext=ciphertext,
        encryption_key_id=cipher.active_key_id,
        encryption_algorithm_version=EVIDENCE_ALGORITHM_VERSION,
        encryption_context_digest=context_digest,
        source_content_digest=source_content_digest,
        integrity_digest="",
    )
    return replace(envelope, integrity_digest=encryption_module._integrity_digest(envelope))


def test_keyring_uses_active_key_for_writes_and_old_key_for_overlap_reads() -> None:
    """Rotation keeps old records readable while every new record uses the active ID."""
    old_key = _key()
    new_key = _key()
    old_cipher = EvidenceCipher(
        None,
        keyring=EvidenceKeyring({"key-2026-07": old_key}, "key-2026-07"),
    )
    old_envelope = old_cipher.encrypt_record("Exact evidence", context=CONTEXT)
    rotated = EvidenceCipher(
        None,
        keyring=EvidenceKeyring(
            {"key-2026-07": old_key, "key-2026-08": new_key},
            "key-2026-08",
        ),
    )

    assert rotated.decrypt_record(old_envelope, context=CONTEXT) == "Exact evidence"
    new_envelope = rotated.encrypt_record("New evidence", context=CONTEXT)
    assert new_envelope.encryption_key_id == "key-2026-08"
    assert rotated.decrypt_record(new_envelope, context=CONTEXT) == "New evidence"

    revoked = EvidenceCipher(
        None,
        keyring=EvidenceKeyring({"key-2026-08": new_key}, "key-2026-08"),
    )
    with pytest.raises(EvidenceDecryptionError, match="key is unavailable"):
        revoked.decrypt_record(old_envelope, context=CONTEXT)


def test_envelope_rejects_context_algorithm_integrity_and_content_tampering() -> None:
    """Every non-secret envelope field is checked before plaintext is returned."""
    cipher = _rotating_cipher()
    envelope = cipher.encrypt_record("Exact evidence", context=CONTEXT)

    with pytest.raises(EvidenceDecryptionError, match="context is invalid"):
        cipher.decrypt_record(
            replace(envelope, encryption_context_digest="0" * 64),
            context=CONTEXT,
        )
    with pytest.raises(EvidenceDecryptionError, match="integrity digest"):
        cipher.decrypt_record(replace(envelope, integrity_digest="0" * 64), context=CONTEXT)
    with pytest.raises(EvidenceDecryptionError, match="algorithm is unsupported"):
        cipher.decrypt_record(
            replace(envelope, encryption_algorithm_version="future-v2"),
            context=CONTEXT,
        )
    with pytest.raises(ValueError, match="context identifiers"):
        make_evidence_context(" tenant-a", RECORD_ID)
    content_tampered = replace(envelope, source_content_digest="0" * 64)
    content_tampered = replace(
        content_tampered,
        integrity_digest=encryption_module._integrity_digest(content_tampered),
    )
    with pytest.raises(EvidenceDecryptionError, match="content digest"):
        cipher.decrypt_record(content_tampered, context=CONTEXT)
    ciphertext_tampered = replace(envelope, ciphertext=b"not-a-token")
    ciphertext_tampered = replace(
        ciphertext_tampered,
        integrity_digest=encryption_module._integrity_digest(ciphertext_tampered),
    )
    with pytest.raises(EvidenceDecryptionError, match="ciphertext is invalid"):
        cipher.decrypt_record(ciphertext_tampered, context=CONTEXT)


def test_legacy_envelope_is_explicit_and_does_not_require_context_binding() -> None:
    """Existing single-key ciphertext remains readable only as declared legacy data."""
    key = _key()
    cipher = EvidenceCipher(None, keyring=EvidenceKeyring.from_single(key))
    envelope = EncryptedEvidence(
        ciphertext=cipher.encrypt("Legacy evidence"),
        encryption_key_id="legacy-v1",
        encryption_algorithm_version=LEGACY_EVIDENCE_ALGORITHM_VERSION,
        encryption_context_digest="",
        source_content_digest="",
        integrity_digest="",
    )

    assert cipher.decrypt_record(envelope, context="ignored") == "Legacy evidence"
    with pytest.raises(EvidenceDecryptionError, match="content digest"):
        cipher.decrypt_record(
            replace(envelope, source_content_digest="0" * 64),
            context="ignored",
        )


def test_invalid_envelope_shapes_fail_closed() -> None:
    """Malformed JSON, wrong context claims, and non-text payloads never reach callers."""
    cipher = _rotating_cipher()
    digest = sha256(b"Exact evidence").hexdigest()
    malformed = _invalid_envelope(
        cipher,
        b"not-json",
        context_digest=encryption_module._digest_text(CONTEXT),
        source_content_digest=digest,
    )
    with pytest.raises(EvidenceDecryptionError, match="envelope is malformed"):
        cipher.decrypt_record(malformed, context=CONTEXT)

    wrong_context = _invalid_envelope(
        cipher,
        {"context_digest": "wrong", "payload": "Exact evidence"},
        context_digest=encryption_module._digest_text(CONTEXT),
        source_content_digest=digest,
    )
    with pytest.raises(EvidenceDecryptionError, match="envelope context"):
        cipher.decrypt_record(wrong_context, context=CONTEXT)

    non_text = _invalid_envelope(
        cipher,
        {"context_digest": encryption_module._digest_text(CONTEXT), "payload": 42},
        context_digest=encryption_module._digest_text(CONTEXT),
        source_content_digest=digest,
    )
    with pytest.raises(EvidenceDecryptionError, match="payload is invalid"):
        cipher.decrypt_record(non_text, context=CONTEXT)


def test_keyring_configuration_validation_and_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Key inventories reject ambiguity and load only the explicit active ID."""
    key = _key().decode("ascii")
    assert EvidenceKeyring.from_environment() is None
    with pytest.raises(ValueError, match="configured together"):
        monkeypatch.setenv("CWL_GRC_EVIDENCE_ACTIVE_KEY_ID", "key-1")
        EvidenceKeyring.from_environment()
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEYRING_JSON", "{")
    with pytest.raises(ValueError, match="malformed"):
        EvidenceKeyring.from_environment()
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEYRING_JSON", json.dumps(["not-a-map"]))
    monkeypatch.setenv("CWL_GRC_EVIDENCE_ACTIVE_KEY_ID", "key-1")
    with pytest.raises(ValueError, match="map key IDs"):
        EvidenceKeyring.from_environment()
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEYRING_JSON", json.dumps({"key-1": key}))
    ring = EvidenceKeyring.from_environment()
    assert ring is not None
    assert ring.active_key_id == "key-1"
    assert ring.key_ids == frozenset({"key-1"})
    with pytest.raises(ValueError, match="active key"):
        EvidenceKeyring({"key-1": key}, "key-2")
    with pytest.raises(ValueError, match="needs one key"):
        EvidenceKeyring({}, "key-1")
    with pytest.raises(ValueError, match="exact non-empty"):
        EvidenceKeyring({" key-1": key}, " key-1")
    with pytest.raises(ValueError, match="key material"):
        EvidenceKeyring({"key-1": object()}, "key-1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="valid Fernet"):
        EvidenceKeyring({"key-1": "invalid"}, "key-1")
    with pytest.raises(ValueError, match="one evidence key"):
        EvidenceCipher(key, keyring=ring)


def test_application_accepts_explicit_and_environment_keyrings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application startup accepts injected or process-configured key inventories."""
    key = _key().decode("ascii")
    ring = EvidenceKeyring({"key-1": key}, "key-1")
    explicit = create_app(database_url="sqlite://", evidence_keyring=ring)
    assert explicit.state.evidence_cipher.active_key_id == "key-1"
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEYRING_JSON", json.dumps({"key-2": key}))
    monkeypatch.setenv("CWL_GRC_EVIDENCE_ACTIVE_KEY_ID", "key-2")
    configured = create_app(database_url="sqlite://")
    assert configured.state.evidence_cipher.active_key_id == "key-2"


def test_new_evidence_records_store_versioned_metadata_and_rewrap_idempotently() -> None:
    """New writes and an interrupted-safe rewrap preserve exact payloads and audit outcomes."""
    factory = _seeded_factory()
    old_key = _key()
    new_key = _key()
    old_cipher = EvidenceCipher(
        None,
        keyring=EvidenceKeyring({"key-2026-07": old_key}, "key-2026-07"),
    )
    decision = AuthorizationDecision("officer-a", PurposeCode.EVIDENCE_BINDING, TENANT_ID)
    with factory() as session:
        record = create_evidence_record(
            session,
            old_cipher,
            decision,
            "Quarterly access review",
            "Exact officer evidence.",
        )
        assert record.encryption_key_id == "key-2026-07"
        assert record.encryption_algorithm_version == EVIDENCE_ALGORITHM_VERSION
        assert old_cipher.decrypt_record(
            record_encryption_envelope(record),
            context=make_evidence_context(TENANT_ID, record.evidence_record_id),
        ) == "Exact officer evidence."
        session.commit()
        record_id = record.evidence_record_id

    rotated = EvidenceCipher(
        None,
        keyring=EvidenceKeyring(
            {"key-2026-07": old_key, "key-2026-08": new_key},
            "key-2026-08",
        ),
    )
    with factory() as session:
        result = rewrap_evidence_records(session, rotated, decision)
        assert result.scanned_count == 1
        assert result.rewrapped_count == 1
        assert result.failed_count == 0
        session.commit()

    with factory() as session:
        record = session.get(EvidenceRecord, record_id)
        assert record is not None
        assert record.encryption_key_id == "key-2026-08"
        assert rotated.decrypt_record(
            record_encryption_envelope(record),
            context=make_evidence_context(TENANT_ID, record.evidence_record_id),
        ) == "Exact officer evidence."
        second = rewrap_evidence_records(session, rotated, decision)
        assert second.rewrapped_count == 0
        after = rewrap_evidence_records(
            session,
            rotated,
            decision,
            after_record_id=record_id,
        )
        assert after.scanned_count == 0
        actions = session.execute(
            text(
                "SELECT action_name FROM audit_event "
                "WHERE resource_identifier = :record_id ORDER BY recorded_at"
            ),
            {"record_id": record_id},
        ).scalars().all()
        assert actions == ["create_evidence", "rewrap_evidence"]


def test_rewrap_records_fail_closed_and_validates_batch_size() -> None:
    """Revoked keys produce an audited failure while invalid batches are rejected."""
    factory = _seeded_factory()
    cipher = EvidenceCipher(None, allow_ephemeral=True)
    decision = AuthorizationDecision("officer-a", PurposeCode.EVIDENCE_BINDING, TENANT_ID)
    with factory() as session:
        record = create_evidence_record(
            session,
            cipher,
            decision,
            "Evidence",
            "Exact text.",
        )
        record.encryption_key_id = "revoked-key"
        with pytest.raises(ValueError, match="batch size"):
            rewrap_evidence_records(session, cipher, decision, batch_size=0)
        result = rewrap_evidence_records(session, cipher, decision)
        assert result.failed_record_ids == (record.evidence_record_id,)
        assert result.failed_count == 1
        actions = session.execute(
            text(
                "SELECT action_name FROM audit_event "
                "WHERE resource_identifier = :record_id"
            ),
            {"record_id": record.evidence_record_id},
        ).scalars().all()
        assert actions[-1] == "rewrap_failed"
        session.rollback()


def test_legacy_evidence_migration_adds_key_metadata(tmp_path: Path) -> None:
    """Existing evidence rows receive explicit legacy metadata during upgrade."""
    from sqlalchemy import create_engine, inspect

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-evidence.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE policy_document ("
                "policy_document_id VARCHAR(64) PRIMARY KEY, "
                "policy_title VARCHAR(255) NOT NULL, "
                "created_by_actor VARCHAR(128) NOT NULL, "
                "created_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE policy_version ("
                "policy_version_id VARCHAR(64) PRIMARY KEY, "
                "policy_document_id VARCHAR(64) NOT NULL, "
                "version_number INTEGER NOT NULL, "
                "policy_body TEXT NOT NULL, "
                "authored_by_actor VARCHAR(128) NOT NULL, "
                "authored_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE evidence_record ("
                "evidence_record_id VARCHAR(64) PRIMARY KEY, "
                "tenant_id VARCHAR(128) NOT NULL, "
                "evidence_title VARCHAR(255) NOT NULL, "
                "collector_actor VARCHAR(128) NOT NULL, "
                "purpose_code VARCHAR(64) NOT NULL, "
                "ciphertext_payload BLOB NOT NULL, "
                "collected_at TIMESTAMP NOT NULL)"
            )
        )
    apply_schema_migrations(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("evidence_record")}
    assert "encryption_key_id" in columns
    assert "encryption_algorithm_version" in columns
    assert "integrity_digest" in columns
