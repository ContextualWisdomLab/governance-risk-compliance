"""Cross-layer bounds for Keyverse provider loading and access-token verification."""

from __future__ import annotations

import pytest

from cwl_grc.keyverse_provider_loader import KeyverseProviderLoaderSettings


ISSUER = "https://identity.example.test/realms/cwl"


def test_provider_settings_cannot_exceed_verifier_jwk_limit() -> None:
    """The loader must not accept a JWK size its verifier always rejects."""
    with pytest.raises(ValueError, match="JWK size"):
        KeyverseProviderLoaderSettings(
            issuer=ISSUER,
            allowed_jwks_hosts=frozenset({"keys.example.test"}),
            jwks_maximum_bytes=(1024 * 1024) + 1,
        )
