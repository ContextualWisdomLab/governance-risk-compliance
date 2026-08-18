"""Encrypt evidence payloads at rest while keeping authorized PII usable."""

from __future__ import annotations

from cryptography.fernet import Fernet


class EvidenceCipher:
    """Fernet wrapper for evidence ciphertext.

    Authorized officers receive the plaintext. The product does not mask PII.
    """

    def __init__(self, evidence_key: str | None) -> None:
        """Use the configured key, or an ephemeral key for standalone demos."""
        if evidence_key:
            self._fernet = Fernet(evidence_key.encode("ascii"))
            self.uses_ephemeral_key = False
        else:
            self._fernet = Fernet(Fernet.generate_key())
            self.uses_ephemeral_key = True

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt usable evidence text, including officer contact PII."""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Return the original evidence text without masking."""
        return self._fernet.decrypt(ciphertext).decode("utf-8")
