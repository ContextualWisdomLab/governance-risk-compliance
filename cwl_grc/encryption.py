"""Encrypt evidence payloads at rest while keeping authorized PII usable."""

from __future__ import annotations

from cryptography.fernet import Fernet


class EvidenceCipher:
    """Fernet wrapper for exact operational evidence ciphertext."""

    def __init__(
        self,
        evidence_key: str | None,
        *,
        allow_ephemeral: bool = False,
    ) -> None:
        """Require durable key material unless an in-memory test explicitly opts in."""
        if evidence_key:
            self._fernet = Fernet(evidence_key.encode("ascii"))
            self.uses_ephemeral_key = False
            return
        if not allow_ephemeral:
            raise ValueError(
                "A durable evidence key is required; set CWL_GRC_EVIDENCE_KEY."
            )
        self._fernet = Fernet(Fernet.generate_key())
        self.uses_ephemeral_key = True

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt usable evidence text, including officer contact PII."""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Return the original evidence text without destructive masking."""
        return self._fernet.decrypt(ciphertext).decode("utf-8")
