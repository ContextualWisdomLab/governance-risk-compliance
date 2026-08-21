"""Encrypt evidence payloads with explicit key and context metadata."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from types import MappingProxyType

from cryptography.fernet import Fernet, InvalidToken


EVIDENCE_ALGORITHM_VERSION = "fernet-v1"
LEGACY_EVIDENCE_ALGORITHM_VERSION = "fernet-v1-legacy"
LEGACY_EVIDENCE_KEY_ID = "legacy-v1"


class EvidenceDecryptionError(ValueError):
    """Indicate that evidence metadata, context, key, or ciphertext is invalid."""


@dataclass(frozen=True)
class EncryptedEvidence:
    """Carry ciphertext and non-secret metadata required for exact decryption."""

    ciphertext: bytes
    encryption_key_id: str
    encryption_algorithm_version: str
    encryption_context_digest: str
    source_content_digest: str
    integrity_digest: str


class EvidenceKeyring:
    """Hold an active key plus bounded read-only predecessor keys."""

    def __init__(self, keys: Mapping[str, str | bytes], active_key_id: str) -> None:
        """Validate one explicit key inventory without persisting raw key material."""
        if not keys:
            raise ValueError("The evidence keyring needs one key.")
        _validate_key_id(active_key_id)
        if active_key_id not in keys:
            raise ValueError("The evidence keyring active key is not configured.")
        parsed: dict[str, Fernet] = {}
        for key_id, material in keys.items():
            _validate_key_id(key_id)
            if isinstance(material, bytes):
                encoded = material
            elif isinstance(material, str):
                encoded = material.encode("ascii")
            else:
                raise ValueError("Evidence key material must be text or bytes.")
            try:
                parsed[key_id] = Fernet(encoded)
            except (TypeError, ValueError) as exc:
                raise ValueError("Evidence key material is not a valid Fernet key.") from exc
        self._keys = MappingProxyType(parsed)
        self._active_key_id = active_key_id

    @classmethod
    def from_single(
        cls,
        evidence_key: str | bytes,
        *,
        key_id: str = LEGACY_EVIDENCE_KEY_ID,
    ) -> EvidenceKeyring:
        """Create a one-key ring for compatibility or an explicit first key version."""
        return cls({key_id: evidence_key}, active_key_id=key_id)

    @classmethod
    def from_environment(cls) -> EvidenceKeyring | None:
        """Load an optional JSON key inventory from process configuration."""
        raw_keys = os.environ.get("CWL_GRC_EVIDENCE_KEYRING_JSON")
        active_key_id = os.environ.get("CWL_GRC_EVIDENCE_ACTIVE_KEY_ID")
        if raw_keys is None and active_key_id is None:
            return None
        if raw_keys is None or active_key_id is None:
            raise ValueError(
                "CWL_GRC_EVIDENCE_KEYRING_JSON and CWL_GRC_EVIDENCE_ACTIVE_KEY_ID "
                "must be configured together."
            )
        try:
            keys = json.loads(raw_keys)
        except json.JSONDecodeError as exc:
            raise ValueError("CWL_GRC_EVIDENCE_KEYRING_JSON is malformed.") from exc
        if not isinstance(keys, dict) or not all(
            isinstance(key_id, str) and isinstance(material, str)
            for key_id, material in keys.items()
        ):
            raise ValueError("CWL_GRC_EVIDENCE_KEYRING_JSON must map key IDs to strings.")
        return cls(keys, active_key_id)

    @property
    def active_key_id(self) -> str:
        """Return the only key allowed for new evidence writes."""
        return self._active_key_id

    @property
    def key_ids(self) -> frozenset[str]:
        """Return configured identifiers without exposing key material."""
        return frozenset(self._keys)

    def _fernet_for(self, key_id: str) -> Fernet:
        """Return exactly the requested key and never fall back to another key."""
        try:
            return self._keys[key_id]
        except KeyError as exc:
            raise EvidenceDecryptionError("The evidence encryption key is unavailable.") from exc


class EvidenceCipher:
    """Encrypt evidence with one active key and explicit predecessor-key reads."""

    def __init__(
        self,
        evidence_key: str | None,
        *,
        allow_ephemeral: bool = False,
        keyring: EvidenceKeyring | None = None,
    ) -> None:
        """Require durable key material unless an in-memory test explicitly opts in."""
        if keyring is not None and evidence_key is not None:
            raise ValueError("Choose one evidence key or one evidence keyring.")
        if keyring is not None:
            self._keyring = keyring
            self.uses_ephemeral_key = False
            return
        if evidence_key:
            self._keyring = EvidenceKeyring.from_single(evidence_key)
            self.uses_ephemeral_key = False
            return
        if not allow_ephemeral:
            raise ValueError(
                "A durable evidence key is required; set CWL_GRC_EVIDENCE_KEY."
            )
        self._keyring = EvidenceKeyring.from_single(
            Fernet.generate_key(),
            key_id="ephemeral-v1",
        )
        self.uses_ephemeral_key = True

    @property
    def active_key_id(self) -> str:
        """Return the key identifier used for all new evidence writes."""
        return self._keyring.active_key_id

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt usable evidence text, including officer contact PII."""
        return self._keyring._fernet_for(self.active_key_id).encrypt(
            plaintext.encode("utf-8")
        )

    def decrypt(self, ciphertext: bytes) -> str:
        """Return legacy evidence text using the explicitly active key only."""
        return self._decrypt_with_key(ciphertext, self.active_key_id)

    def encrypt_record(self, plaintext: str, *, context: str) -> EncryptedEvidence:
        """Encrypt a new record with authenticated context and content digests."""
        context_digest = _digest_text(context)
        source_content_digest = _digest_text(plaintext)
        envelope = json.dumps(
            {
                "context_digest": context_digest,
                "payload": plaintext,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = self._keyring._fernet_for(self.active_key_id).encrypt(envelope)
        result = EncryptedEvidence(
            ciphertext=ciphertext,
            encryption_key_id=self.active_key_id,
            encryption_algorithm_version=EVIDENCE_ALGORITHM_VERSION,
            encryption_context_digest=context_digest,
            source_content_digest=source_content_digest,
            integrity_digest="",
        )
        return EncryptedEvidence(
            ciphertext=result.ciphertext,
            encryption_key_id=result.encryption_key_id,
            encryption_algorithm_version=result.encryption_algorithm_version,
            encryption_context_digest=result.encryption_context_digest,
            source_content_digest=result.source_content_digest,
            integrity_digest=_integrity_digest(result),
        )

    def decrypt_record(self, envelope: EncryptedEvidence, *, context: str) -> str:
        """Decrypt one record only when key, algorithm, context, and digests match."""
        if envelope.encryption_algorithm_version == LEGACY_EVIDENCE_ALGORITHM_VERSION:
            plaintext = self._decrypt_with_key(
                envelope.ciphertext,
                envelope.encryption_key_id,
            )
            if envelope.source_content_digest and not compare_digest(
                _digest_text(plaintext), envelope.source_content_digest
            ):
                raise EvidenceDecryptionError("The evidence content digest is invalid.")
            return plaintext
        if envelope.encryption_algorithm_version != EVIDENCE_ALGORITHM_VERSION:
            raise EvidenceDecryptionError("The evidence encryption algorithm is unsupported.")
        expected_context_digest = _digest_text(context)
        if not compare_digest(expected_context_digest, envelope.encryption_context_digest):
            raise EvidenceDecryptionError("The evidence encryption context is invalid.")
        if not compare_digest(_integrity_digest(envelope), envelope.integrity_digest):
            raise EvidenceDecryptionError("The evidence integrity digest is invalid.")
        raw_envelope = self._decrypt_with_key(
            envelope.ciphertext,
            envelope.encryption_key_id,
        )
        try:
            payload = json.loads(raw_envelope)
        except json.JSONDecodeError as exc:
            raise EvidenceDecryptionError("The evidence envelope is malformed.") from exc
        if not isinstance(payload, dict) or payload.get("context_digest") != expected_context_digest:
            raise EvidenceDecryptionError("The evidence envelope context is invalid.")
        plaintext = payload.get("payload")
        if not isinstance(plaintext, str):
            raise EvidenceDecryptionError("The evidence envelope payload is invalid.")
        if not compare_digest(_digest_text(plaintext), envelope.source_content_digest):
            raise EvidenceDecryptionError("The evidence content digest is invalid.")
        return plaintext

    def _decrypt_with_key(self, ciphertext: bytes, key_id: str) -> str:
        """Decrypt with the named key and translate cryptographic failures safely."""
        try:
            return self._keyring._fernet_for(key_id).decrypt(ciphertext).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise EvidenceDecryptionError("The evidence ciphertext is invalid.") from exc


def make_evidence_context(tenant_id: str, evidence_record_id: str) -> str:
    """Build the stable tenant-and-record context authenticated by new envelopes."""
    if (
        not isinstance(tenant_id, str)
        or not tenant_id
        or tenant_id != tenant_id.strip()
        or not isinstance(evidence_record_id, str)
        or not evidence_record_id
        or evidence_record_id != evidence_record_id.strip()
    ):
        raise ValueError("Evidence encryption context identifiers must be exact text.")
    return f"{tenant_id}\x00{evidence_record_id}"


def _validate_key_id(key_id: str) -> None:
    """Require an exact non-empty key identifier before it enters the keyring."""
    if not isinstance(key_id, str) or not key_id or key_id != key_id.strip():
        raise ValueError("Evidence key identifiers must be exact non-empty text.")


def _digest_text(value: str) -> str:
    """Return a stable SHA-256 digest without logging or returning source content."""
    return sha256(value.encode("utf-8")).hexdigest()


def _integrity_digest(envelope: EncryptedEvidence) -> str:
    """Digest immutable envelope metadata and ciphertext for tamper detection."""
    material = b"\x00".join(
        (
            envelope.encryption_key_id.encode("utf-8"),
            envelope.encryption_algorithm_version.encode("utf-8"),
            envelope.encryption_context_digest.encode("ascii"),
            envelope.source_content_digest.encode("ascii"),
            envelope.ciphertext,
        )
    )
    return sha256(material).hexdigest()
