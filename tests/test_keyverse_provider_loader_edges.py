"""Edge-path coverage for the bounded Keyverse OIDC provider loader."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import cwl_grc.keyverse_provider_loader as loader_module
from cwl_grc.keyverse_authentication import KeyverseAccessTokenSettings
from cwl_grc.keyverse_provider_loader import (
    KeyverseProviderLoadError,
    KeyverseProviderLoaderSettings,
    PinnedHttpsDocumentFetcher,
    ValidatedHttpsEndpoint,
    _PinnedHttpsConnection,
    _aware_utc,
    _create_pinned_connection,
    _format_host_header,
    _normalize_host,
    _system_resolver,
    build_openid_configuration_url,
    load_keyverse_provider,
    validate_https_endpoint,
)


ISSUER = "https://identity.example.test/realms/cwl"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URL = "https://keys.example.test/jwks"
NOW = datetime(2026, 8, 19, 5, 0, tzinfo=timezone.utc)


def _public_jwks() -> bytes:
    """Return one valid bounded RSA public JWK document."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    return json.dumps({"keys": [jwk]}).encode()


def _metadata(*, issuer: str = ISSUER, jwks_uri: str = JWKS_URL) -> bytes:
    """Return minimal valid OIDC discovery metadata."""
    return json.dumps(
        {
            "issuer": issuer,
            "jwks_uri": jwks_uri,
            "id_token_signing_alg_values_supported": ["RS256"],
            "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        }
    ).encode()


def _resolver(hostname: str, _port: int) -> tuple[str, ...]:
    """Resolve exact test hosts to globally routable fixture addresses."""
    return {
        "identity.example.test": ("1.1.1.1",),
        "keys.example.test": ("8.8.8.8",),
    }[hostname]


class _StaticFetcher:
    """Return exact in-memory metadata or JWK bytes."""

    def __init__(self, documents: dict[str, bytes]) -> None:
        self._documents = documents

    def fetch(self, endpoint: ValidatedHttpsEndpoint, maximum_bytes: int) -> bytes:
        """Return the configured bytes without silently truncating oversized input."""
        document = self._documents[endpoint.url]
        assert maximum_bytes > 0
        return document


class _FailingConnection:
    """Connection double that fails every request and records closure."""

    def __init__(self) -> None:
        self.closed = False

    def request(
        self,
        _method: str,
        _target: str,
        *,
        headers: dict[str, str],
    ) -> None:
        """Simulate an address-level timeout after validating request headers."""
        assert headers["Accept"] == "application/json"
        raise TimeoutError("timed out")

    def getresponse(self) -> Any:
        """Remain unreachable after request failure."""
        raise AssertionError("response must not be requested")

    def close(self) -> None:
        """Record cleanup."""
        self.closed = True


def _settings(**overrides: Any) -> KeyverseProviderLoaderSettings:
    """Return provider-loader settings for the test issuer."""
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "allowed_jwks_hosts": frozenset({"keys.example.test"}),
        "timeout_seconds": 5.0,
        "metadata_maximum_bytes": 64 * 1024,
        "jwks_maximum_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return KeyverseProviderLoaderSettings(**values)


def test_provider_settings_cannot_exceed_verifier_jwk_limit() -> None:
    """The network loader must not admit a JWK limit its verifier always rejects."""
    with pytest.raises(ValueError, match="JWK size"):
        _settings(jwks_maximum_bytes=(1024 * 1024) + 1)


def test_snapshot_verifier_rejects_resource_issuer_mismatch() -> None:
    """A loaded issuer cannot be paired with another resource-server issuer."""
    snapshot = load_keyverse_provider(
        _settings(),
        fetcher=_StaticFetcher(
            {DISCOVERY_URL: _metadata(), JWKS_URL: _public_jwks()}
        ),
        resolver=_resolver,
        now=lambda: NOW,
    )
    mismatched = KeyverseAccessTokenSettings(
        issuer="https://identity.example.test/realms/other",
        audience="cwl-grc-api",
        allowed_client_ids=frozenset({"cwl-grc-web"}),
        allowed_roles=frozenset({"compliance_officer"}),
    )
    with pytest.raises(KeyverseProviderLoadError, match="loaded issuer"):
        snapshot.build_verifier(mismatched)


def test_fetcher_rejects_invalid_timeout_limit_and_total_address_failure() -> None:
    """Transport policy rejects invalid construction, invalid limits, and full outage."""
    for timeout in (0.0, 31.0):
        with pytest.raises(ValueError, match="timeout"):
            PinnedHttpsDocumentFetcher(timeout_seconds=timeout)

    endpoint = ValidatedHttpsEndpoint(
        url=JWKS_URL,
        hostname="keys.example.test",
        port=443,
        request_target="/jwks",
        host_header="keys.example.test",
        addresses=("8.8.8.8", "1.1.1.1"),
    )
    created: list[_FailingConnection] = []

    def factory(_address: str, _port: int, _hostname: str, _timeout: float):  # noqa: ANN202
        connection = _FailingConnection()
        created.append(connection)
        return connection

    fetcher = PinnedHttpsDocumentFetcher(
        timeout_seconds=5.0,
        connection_factory=factory,
    )
    with pytest.raises(ValueError, match="limit"):
        fetcher.fetch(endpoint, maximum_bytes=0)
    with pytest.raises(KeyverseProviderLoadError, match="every pinned address"):
        fetcher.fetch(endpoint, maximum_bytes=128)
    assert len(created) == 2
    assert all(connection.closed for connection in created)


def test_endpoint_requires_host_valid_port_local_rejection_and_safe_path() -> None:
    """Host, port, local-name, IP-literal, and decoded-path failures are explicit."""
    with pytest.raises(KeyverseProviderLoadError, match="host"):
        validate_https_endpoint(
            "https:///jwks",
            allowed_hosts=frozenset({"keys.example.test"}),
            resolver=_resolver,
        )
    with pytest.raises(KeyverseProviderLoadError, match="port"):
        validate_https_endpoint(
            "https://keys.example.test:bad/jwks",
            allowed_hosts=frozenset({"keys.example.test"}),
            resolver=_resolver,
        )

    for hostname in (
        "localhost",
        "service.localhost",
        "internal",
        "service.internal",
        "service.local",
        "127.0.0.1",
    ):
        with pytest.raises(KeyverseProviderLoadError, match="globally routable"):
            validate_https_endpoint(
                f"https://{hostname}/jwks",
                allowed_hosts=frozenset({hostname}),
                resolver=lambda _host, _port: ("8.8.8.8",),
            )

    for url in (
        "https://keys.example.test/%FF",
        "https://keys.example.test/path%00control",
    ):
        with pytest.raises(KeyverseProviderLoadError, match="path"):
            validate_https_endpoint(
                url,
                allowed_hosts=frozenset({"keys.example.test"}),
                resolver=_resolver,
            )


def test_dns_rejects_invalid_answers_and_deduplicates_global_answers() -> None:
    """Malformed DNS answers fail; duplicate global answers remain one pinned dial."""
    with pytest.raises(KeyverseProviderLoadError, match="globally routable"):
        validate_https_endpoint(
            JWKS_URL,
            allowed_hosts=frozenset({"keys.example.test"}),
            resolver=lambda _host, _port: ("not-an-ip",),
        )
    endpoint = validate_https_endpoint(
        JWKS_URL,
        allowed_hosts=frozenset({"keys.example.test"}),
        resolver=lambda _host, _port: ("8.8.8.8", "8.8.8.8", "1.1.1.1"),
    )
    assert endpoint.addresses == ("8.8.8.8", "1.1.1.1")


def test_host_normalization_and_system_resolver_fail_closed() -> None:
    """Hostname normalization and platform DNS failures never broaden authority."""
    assert _normalize_host("KEYS.EXAMPLE.TEST.") == "keys.example.test"
    for hostname in ("", "bad host", "example..test"):
        with pytest.raises(KeyverseProviderLoadError, match="host"):
            _normalize_host(hostname)

    original_getaddrinfo = socket.getaddrinfo
    try:
        socket.getaddrinfo = lambda *_args, **_kwargs: (_ for _ in ()).throw(  # type: ignore[assignment]
            OSError("dns unavailable")
        )
        with pytest.raises(KeyverseProviderLoadError, match="DNS resolution failed"):
            _system_resolver("keys.example.test", 443)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def test_ipv6_host_header_and_connection_constructor_edge_paths() -> None:
    """IPv6 Host rendering and pinned connection construction preserve TLS authority."""
    assert _format_host_header("2001:4860:4860::8888", 443) == "[2001:4860:4860::8888]"
    assert _format_host_header("2001:4860:4860::8888", 8443) == "[2001:4860:4860::8888]:8443"
    assert _format_host_header("keys.example.test", 443) == "keys.example.test"
    assert _format_host_header("keys.example.test", 8443) == "keys.example.test:8443"

    connection = _create_pinned_connection(
        "8.8.8.8",
        443,
        "keys.example.test",
        5.0,
    )
    assert isinstance(connection, _PinnedHttpsConnection)
    connection.close()


def test_aware_utc_rejects_naive_and_normalizes_aware_values() -> None:
    """Refresh timestamps must be timezone-aware and normalized to UTC."""
    naive = datetime(2026, 8, 19, 5, 0)
    with pytest.raises(KeyverseProviderLoadError, match="timezone-aware"):
        _aware_utc(naive)
    assert _aware_utc(NOW) == NOW


def test_metadata_rejects_wrong_shape_missing_fields_and_algorithms() -> None:
    """Discovery metadata needs one exact issuer, JWK endpoint, and RS256 support."""
    invalid_documents = (
        b"[]",
        json.dumps({"issuer": ISSUER}).encode(),
        json.dumps({"issuer": ISSUER, "jwks_uri": JWKS_URL}).encode(),
        json.dumps(
            {
                "issuer": ISSUER,
                "jwks_uri": JWKS_URL,
                "id_token_signing_alg_values_supported": ["ES256"],
            }
        ).encode(),
    )
    for document in invalid_documents:
        with pytest.raises(KeyverseProviderLoadError):
            loader_module._parse_provider_metadata(document, expected_issuer=ISSUER)
