"""Security and rotation regressions for Keyverse OIDC metadata and JWK loading."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cwl_grc.keyverse_authentication import KeyverseAccessTokenSettings
from cwl_grc.keyverse_provider_loader import (
    KeyverseProviderLoadError,
    KeyverseProviderLoaderSettings,
    KeyverseProviderRegistry,
    PinnedHttpsDocumentFetcher,
    build_openid_configuration_url,
    load_keyverse_provider,
    validate_https_endpoint,
)


ISSUER = "https://identity.example.test/realms/cwl"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URL = "https://keys.example.test/realms/cwl/protocol/openid-connect/certs"
NOW = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)


def _rsa_jwk(kid: str) -> tuple[Any, dict[str, Any]]:
    """Return one RSA private key and public signing JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _resolver(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve reviewed test hosts to globally routable fixture addresses."""
    assert port == 443
    mapping = {
        "identity.example.test": ("1.1.1.1",),
        "keys.example.test": ("8.8.8.8", "2001:4860:4860::8888"),
    }
    return mapping[hostname]


def _settings(**overrides: Any) -> KeyverseProviderLoaderSettings:
    """Return one strict provider-loading policy."""
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "allowed_jwks_hosts": frozenset({"keys.example.test"}),
        "timeout_seconds": 5.0,
        "metadata_maximum_bytes": 64 * 1024,
        "jwks_maximum_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return KeyverseProviderLoaderSettings(**values)


class _StaticFetcher:
    """Return reviewed in-memory documents while recording endpoint contracts."""

    def __init__(self, documents: dict[str, bytes]) -> None:
        self.documents = documents
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []

    def fetch(self, endpoint, maximum_bytes: int) -> bytes:  # noqa: ANN001
        """Return one configured document and record the pinned addresses."""
        self.calls.append((endpoint.url, maximum_bytes, endpoint.addresses))
        return self.documents[endpoint.url]


class _FakeResponse:
    """Minimal HTTP response used to exercise bounded transport behavior."""

    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
        content_length: str | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": content_type,
            **({"Content-Length": content_length} if content_length is not None else {}),
        }

    def getheader(self, name: str) -> str | None:
        """Return one case-insensitive response header."""
        for key, value in self.headers.items():
            if key.casefold() == name.casefold():
                return value
        return None

    def read(self, amount: int) -> bytes:
        """Return at most the requested bytes."""
        return self.body[:amount]


class _FakeConnection:
    """Record one pinned HTTPS request and expose a configured response."""

    def __init__(self, response: _FakeResponse, *, fail: Exception | None = None) -> None:
        self.response = response
        self.fail = fail
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, target: str, headers: dict[str, str]) -> None:
        """Record the request or simulate a transport failure."""
        if self.fail is not None:
            raise self.fail
        self.requests.append((method, target, headers))

    def getresponse(self) -> _FakeResponse:
        """Return the configured response."""
        return self.response

    def close(self) -> None:
        """Record deterministic connection cleanup."""
        self.closed = True


def test_discovery_url_preserves_issuer_path_and_exact_root() -> None:
    """OIDC Discovery appends the well-known suffix after the issuer path."""
    assert build_openid_configuration_url(ISSUER) == DISCOVERY_URL
    assert build_openid_configuration_url(f"{ISSUER}/") == DISCOVERY_URL
    assert build_openid_configuration_url("https://identity.example.test") == (
        "https://identity.example.test/.well-known/openid-configuration"
    )


def test_loader_settings_reject_ambiguous_or_unbounded_configuration() -> None:
    """Issuer, JWK allowlist, timeouts, and document bounds are explicit."""
    invalid_cases = (
        ({"issuer": "http://identity.example.test"}, "HTTPS issuer"),
        ({"issuer": f"{ISSUER}?query=1"}, "HTTPS issuer"),
        ({"issuer": f"{ISSUER}#fragment"}, "HTTPS issuer"),
        ({"allowed_jwks_hosts": frozenset()}, "JWK host"),
        ({"allowed_jwks_hosts": frozenset({""})}, "JWK host"),
        ({"timeout_seconds": True}, "timeout"),
        ({"timeout_seconds": 0}, "timeout"),
        ({"timeout_seconds": 31}, "timeout"),
        ({"metadata_maximum_bytes": True}, "metadata size"),
        ({"metadata_maximum_bytes": 0}, "metadata size"),
        ({"metadata_maximum_bytes": 1024 * 1024 + 1}, "metadata size"),
        ({"jwks_maximum_bytes": True}, "JWK size"),
        ({"jwks_maximum_bytes": 0}, "JWK size"),
        ({"jwks_maximum_bytes": 4 * 1024 * 1024 + 1}, "JWK size"),
    )
    for overrides, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            _settings(**overrides)


def test_https_endpoint_is_allowlisted_normalized_and_dns_pinned() -> None:
    """A safe endpoint has one exact host and reviewed global DNS results."""
    endpoint = validate_https_endpoint(
        JWKS_URL,
        allowed_hosts=frozenset({"KEYS.EXAMPLE.TEST."}),
        resolver=_resolver,
    )
    assert endpoint.url == JWKS_URL
    assert endpoint.hostname == "keys.example.test"
    assert endpoint.port == 443
    assert endpoint.request_target == "/realms/cwl/protocol/openid-connect/certs"
    assert endpoint.host_header == "keys.example.test"
    assert endpoint.addresses == ("8.8.8.8", "2001:4860:4860::8888")


def test_https_endpoint_rejects_untrusted_url_and_resolution_shapes() -> None:
    """SSRF, userinfo, redirects-by-query, local names, and DNS failure fail closed."""
    invalid_urls = (
        ("http://keys.example.test/jwks", "https"),
        ("https://user@keys.example.test/jwks", "userinfo"),
        ("https://keys.example.test/jwks?next=internal", "query"),
        ("https://keys.example.test/jwks#fragment", "fragment"),
        ("https://other.example.test/jwks", "allowlist"),
        ("https://localhost/jwks", "allowlist"),
        ("https://127.0.0.1/jwks", "allowlist"),
        ("https://keys.example.test:0/jwks", "port"),
        ("https://keys.example.test/%2e%2e/admin", "path"),
        ("https://keys.example.test/path%2fadmin", "path"),
        ("https://keys.example.test/path\\admin", "path"),
    )
    for url, message in invalid_urls:
        with pytest.raises(KeyverseProviderLoadError, match=message):
            validate_https_endpoint(
                url,
                allowed_hosts=frozenset({"keys.example.test"}),
                resolver=_resolver,
            )

    def private_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("10.0.0.7",)

    def empty_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        return ()

    def failing_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        raise socket.gaierror("unavailable")

    for resolver, message in (
        (private_resolver, "globally routable"),
        (empty_resolver, "resolve"),
        (failing_resolver, "resolve"),
    ):
        with pytest.raises(KeyverseProviderLoadError, match=message):
            validate_https_endpoint(
                JWKS_URL,
                allowed_hosts=frozenset({"keys.example.test"}),
                resolver=resolver,
            )


def test_provider_loader_validates_metadata_jwks_hashes_and_rotation() -> None:
    """A complete snapshot binds exact issuer metadata, public keys, and hashes."""
    _old_private, old_jwk = _rsa_jwk("old-key")
    _new_private, new_jwk = _rsa_jwk("new-key")
    metadata = json.dumps(
        {
            "issuer": ISSUER,
            "jwks_uri": JWKS_URL,
            "id_token_signing_alg_values_supported": ["RS256", "PS256"],
        },
        separators=(",", ":"),
    ).encode()
    jwks = json.dumps(
        {"keys": [old_jwk, new_jwk]},
        separators=(",", ":"),
    ).encode()
    fetcher = _StaticFetcher({DISCOVERY_URL: metadata, JWKS_URL: jwks})

    snapshot = load_keyverse_provider(
        _settings(),
        fetcher=fetcher,
        resolver=_resolver,
        now=lambda: NOW,
    )

    assert snapshot.metadata.issuer == ISSUER
    assert snapshot.metadata.jwks_uri == JWKS_URL
    assert snapshot.metadata.id_token_signing_algorithms == frozenset({"RS256", "PS256"})
    assert set(snapshot.key_set.keys_by_id) == {"old-key", "new-key"}
    assert snapshot.loaded_at == NOW
    assert snapshot.metadata_sha256.startswith("sha256:")
    assert snapshot.jwks_sha256.startswith("sha256:")
    assert snapshot.discovery_endpoint.url == DISCOVERY_URL
    assert snapshot.jwks_endpoint.url == JWKS_URL
    assert fetcher.calls == [
        (DISCOVERY_URL, 64 * 1024, ("1.1.1.1",)),
        (JWKS_URL, 1024 * 1024, ("8.8.8.8", "2001:4860:4860::8888")),
    ]

    access_settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience="cwl-grc-api",
        allowed_client_ids=frozenset({"cwl-grc-web"}),
        allowed_roles=frozenset({"compliance_officer"}),
    )
    verifier = snapshot.build_verifier(access_settings, now=lambda: NOW)
    assert verifier is not None


def test_provider_loader_rejects_metadata_drift_and_malformed_documents() -> None:
    """Wrong issuer, unsafe JWK URL, algorithms, and JSON shapes abort the load."""
    _private_key, jwk = _rsa_jwk("key-1")
    valid_jwks = json.dumps({"keys": [jwk]}).encode()
    invalid_metadata = (
        (b"not-json", "metadata"),
        (b"[]", "object"),
        (json.dumps({"issuer": ISSUER}).encode(), "jwks_uri"),
        (
            json.dumps(
                {
                    "issuer": f"{ISSUER}/",
                    "jwks_uri": JWKS_URL,
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            ).encode(),
            "issuer",
        ),
        (
            json.dumps(
                {
                    "issuer": ISSUER,
                    "jwks_uri": "http://keys.example.test/jwks",
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            ).encode(),
            "https",
        ),
        (
            json.dumps(
                {
                    "issuer": ISSUER,
                    "jwks_uri": JWKS_URL,
                    "id_token_signing_alg_values_supported": ["PS256"],
                }
            ).encode(),
            "RS256",
        ),
        (
            json.dumps(
                {
                    "issuer": ISSUER,
                    "jwks_uri": JWKS_URL,
                    "id_token_signing_alg_values_supported": "RS256",
                }
            ).encode(),
            "algorithm",
        ),
    )
    for metadata, message in invalid_metadata:
        fetcher = _StaticFetcher({DISCOVERY_URL: metadata, JWKS_URL: valid_jwks})
        with pytest.raises(KeyverseProviderLoadError, match=message):
            load_keyverse_provider(
                _settings(),
                fetcher=fetcher,
                resolver=_resolver,
                now=lambda: NOW,
            )

    oversized = _StaticFetcher(
        {
            DISCOVERY_URL: b"x" * (64 * 1024 + 1),
            JWKS_URL: valid_jwks,
        }
    )
    with pytest.raises(KeyverseProviderLoadError, match="metadata.*too large"):
        load_keyverse_provider(
            _settings(),
            fetcher=oversized,
            resolver=_resolver,
            now=lambda: NOW,
        )


def test_pinned_fetcher_refuses_redirects_content_type_and_oversize() -> None:
    """Production transport is GET-only, redirect-free, JSON-only, and bounded."""
    endpoint = validate_https_endpoint(
        JWKS_URL,
        allowed_hosts=frozenset({"keys.example.test"}),
        resolver=_resolver,
    )

    scenarios = (
        (_FakeResponse(b"{}", status=302), "HTTP 302"),
        (_FakeResponse(b"{}", content_type="text/html"), "application/json"),
        (_FakeResponse(b"{}", content_length="not-a-number"), "Content-Length"),
        (_FakeResponse(b"{}", content_length="100"), "too large"),
        (_FakeResponse(b"01234567890"), "too large"),
    )
    for response, message in scenarios:
        connection = _FakeConnection(response)
        fetcher = PinnedHttpsDocumentFetcher(
            timeout_seconds=5.0,
            connection_factory=lambda *_args, **_kwargs: connection,
        )
        with pytest.raises(KeyverseProviderLoadError, match=message):
            fetcher.fetch(endpoint, maximum_bytes=10)
        assert connection.closed is True


def test_pinned_fetcher_fails_over_addresses_and_sends_closed_headers() -> None:
    """A failed pinned address does not change host identity or widen the request."""
    endpoint = validate_https_endpoint(
        JWKS_URL,
        allowed_hosts=frozenset({"keys.example.test"}),
        resolver=_resolver,
    )
    first = _FakeConnection(_FakeResponse(b"{}"), fail=OSError("first failed"))
    second = _FakeConnection(_FakeResponse(b'{"keys":[]}'))
    connections = iter((first, second))
    factory_calls: list[tuple[str, int, str, float]] = []

    def factory(address: str, port: int, hostname: str, timeout: float):  # noqa: ANN202
        factory_calls.append((address, port, hostname, timeout))
        return next(connections)

    fetcher = PinnedHttpsDocumentFetcher(
        timeout_seconds=5.0,
        connection_factory=factory,
    )
    assert fetcher.fetch(endpoint, maximum_bytes=128) == b'{"keys":[]}'
    assert first.closed is True
    assert second.closed is True
    assert factory_calls == [
        ("8.8.8.8", 443, "keys.example.test", 5.0),
        ("2001:4860:4860::8888", 443, "keys.example.test", 5.0),
    ]
    assert second.requests == [
        (
            "GET",
            "/realms/cwl/protocol/openid-connect/certs",
            {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Host": "keys.example.test",
                "User-Agent": "cwl-grc-keyverse-loader/0.1",
            },
        )
    ]


def test_registry_is_atomic_monotonic_and_issuer_bound() -> None:
    """Failed or stale refreshes never replace the last reviewed provider snapshot."""
    _private_key, jwk = _rsa_jwk("key-1")
    metadata = json.dumps(
        {
            "issuer": ISSUER,
            "jwks_uri": JWKS_URL,
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    ).encode()
    jwks = json.dumps({"keys": [jwk]}).encode()
    fetcher = _StaticFetcher({DISCOVERY_URL: metadata, JWKS_URL: jwks})
    first = load_keyverse_provider(
        _settings(),
        fetcher=fetcher,
        resolver=_resolver,
        now=lambda: NOW,
    )
    later = load_keyverse_provider(
        _settings(),
        fetcher=fetcher,
        resolver=_resolver,
        now=lambda: NOW + timedelta(minutes=1),
    )

    registry = KeyverseProviderRegistry()
    with pytest.raises(KeyverseProviderLoadError, match="not loaded"):
        registry.current()
    registry.replace(first)
    assert registry.current() is first
    registry.replace(later)
    assert registry.current() is later
    with pytest.raises(KeyverseProviderLoadError, match="newer"):
        registry.replace(first)

    other_metadata = json.dumps(
        {
            "issuer": "https://identity.example.test/realms/other",
            "jwks_uri": JWKS_URL,
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    ).encode()
    other_discovery = (
        "https://identity.example.test/realms/other/.well-known/openid-configuration"
    )
    other = load_keyverse_provider(
        _settings(issuer="https://identity.example.test/realms/other"),
        fetcher=_StaticFetcher({other_discovery: other_metadata, JWKS_URL: jwks}),
        resolver=_resolver,
        now=lambda: NOW + timedelta(minutes=2),
    )
    with pytest.raises(KeyverseProviderLoadError, match="issuer"):
        registry.replace(other)
    assert registry.current() is later
