"""Load exact Keyverse OIDC metadata and public JWKs through a pinned HTTPS boundary."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from cwl_grc.keyverse_authentication import (
    MAX_JWKS_BYTES as ACCESS_TOKEN_MAX_JWKS_BYTES,
    AccessTokenValidationError,
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    KeyverseJwkSet,
    parse_keyverse_jwks,
)


MAX_METADATA_BYTES = 1024 * 1024
MAX_JWKS_BYTES = ACCESS_TOKEN_MAX_JWKS_BYTES
MAX_TIMEOUT_SECONDS = 30.0
USER_AGENT = "cwl-grc-keyverse-loader/0.1"


class KeyverseProviderLoadError(ValueError):
    """Signal that provider metadata, transport, or refresh policy failed closed."""


@dataclass(frozen=True)
class ValidatedHttpsEndpoint:
    """One exact HTTPS target with its DNS results pinned for the request."""

    url: str
    hostname: str
    port: int
    request_target: str
    host_header: str
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class KeyverseProviderLoaderSettings:
    """Bounded network and document policy for one exact Keyverse issuer."""

    issuer: str
    allowed_jwks_hosts: frozenset[str]
    timeout_seconds: float = 5.0
    metadata_maximum_bytes: int = 64 * 1024
    jwks_maximum_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        """Normalize immutable host policy and reject unsafe resource bounds."""
        _validate_issuer_syntax(self.issuer)
        normalized_hosts = frozenset(
            _normalize_host(host) for host in self.allowed_jwks_hosts if host.strip()
        )
        if not normalized_hosts or len(normalized_hosts) != len(
            self.allowed_jwks_hosts
        ):
            raise ValueError("Keyverse requires a non-empty JWK host allowlist.")
        object.__setattr__(self, "allowed_jwks_hosts", normalized_hosts)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "Keyverse timeout must be greater than 0 and at most 30 seconds."
            )
        if (
            isinstance(self.metadata_maximum_bytes, bool)
            or not isinstance(self.metadata_maximum_bytes, int)
            or not 0 < self.metadata_maximum_bytes <= MAX_METADATA_BYTES
        ):
            raise ValueError("Keyverse metadata size must be between 1 byte and 1 MiB.")
        if (
            isinstance(self.jwks_maximum_bytes, bool)
            or not isinstance(self.jwks_maximum_bytes, int)
            or not 0 < self.jwks_maximum_bytes <= MAX_JWKS_BYTES
        ):
            raise ValueError("Keyverse JWK size must be between 1 byte and 1 MiB.")


@dataclass(frozen=True)
class KeyverseProviderMetadata:
    """Validated minimum OIDC metadata required by the GRC resource server."""

    issuer: str
    jwks_uri: str
    id_token_signing_algorithms: frozenset[str]
    additional_claims: Mapping[str, Any]


@dataclass(frozen=True)
class KeyverseProviderSnapshot:
    """One immutable, hash-addressed provider configuration and public-key view."""

    metadata: KeyverseProviderMetadata
    key_set: KeyverseJwkSet
    discovery_endpoint: ValidatedHttpsEndpoint
    jwks_endpoint: ValidatedHttpsEndpoint
    metadata_sha256: str
    jwks_sha256: str
    loaded_at: datetime

    def build_verifier(
        self,
        settings: KeyverseAccessTokenSettings,
        *,
        now: Callable[[], datetime] | None = None,
        token_replay_guard: Callable[[str], bool] | None = None,
    ) -> KeyverseAccessTokenVerifier:
        """Build a token verifier only when resource and discovery issuers agree."""
        if settings.issuer != self.metadata.issuer:
            raise KeyverseProviderLoadError(
                "Keyverse verifier settings do not match the loaded issuer."
            )
        return KeyverseAccessTokenVerifier(
            settings,
            self.key_set,
            now=now,
            token_replay_guard=token_replay_guard,
        )


class KeyverseDocumentFetcher(Protocol):
    """Port for retrieving one already validated and DNS-pinned HTTPS document."""

    def fetch(
        self,
        endpoint: ValidatedHttpsEndpoint,
        maximum_bytes: int,
    ) -> bytes:
        """Return exact response bytes or fail without following redirects."""
        ...


class _ConnectionLike(Protocol):
    """Narrow connection contract used by the pinned document fetcher."""

    def request(self, method: str, target: str, headers: dict[str, str]) -> None:
        """Issue one request."""
        ...

    def getresponse(self) -> Any:
        """Return one response object."""
        ...

    def close(self) -> None:
        """Close the transport."""
        ...


ConnectionFactory = Callable[[str, int, str, float], _ConnectionLike]
Resolver = Callable[[str, int], Sequence[str]]


class PinnedHttpsDocumentFetcher:
    """Fetch JSON over TLS using pre-resolved addresses and the original SNI host."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        """Configure one bounded timeout and injectable pinned-connection factory."""
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError(
                "Keyverse timeout must be greater than 0 and at most 30 seconds."
            )
        self._timeout_seconds = timeout_seconds
        self._connection_factory = connection_factory or _create_pinned_connection

    def fetch(
        self,
        endpoint: ValidatedHttpsEndpoint,
        maximum_bytes: int,
    ) -> bytes:
        """Return one redirect-free application/json response within the byte limit."""
        if maximum_bytes <= 0:
            raise ValueError("Keyverse document limit must be positive.")
        last_transport_error: Exception | None = None
        for address in endpoint.addresses:
            connection = self._connection_factory(
                address,
                endpoint.port,
                endpoint.hostname,
                self._timeout_seconds,
            )
            try:
                connection.request(
                    "GET",
                    endpoint.request_target,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "Host": endpoint.host_header,
                        "User-Agent": USER_AGENT,
                    },
                )
                response = connection.getresponse()
                status = int(response.status)
                if status != 200:
                    raise KeyverseProviderLoadError(
                        f"Keyverse endpoint returned HTTP {status}; redirects are refused."
                    )
                content_type = response.getheader("Content-Type")
                media_type = (
                    content_type.split(";", maxsplit=1)[0].strip().casefold()
                    if isinstance(content_type, str)
                    else ""
                )
                if media_type != "application/json":
                    raise KeyverseProviderLoadError(
                        "Keyverse endpoint must return application/json."
                    )
                content_length = response.getheader("Content-Length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except (TypeError, ValueError) as exc:
                        raise KeyverseProviderLoadError(
                            "Keyverse Content-Length is invalid."
                        ) from exc
                    if declared_length < 0 or declared_length > maximum_bytes:
                        raise KeyverseProviderLoadError(
                            "Keyverse response is too large."
                        )
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    raise KeyverseProviderLoadError("Keyverse response is too large.")
                return bytes(body)
            except KeyverseProviderLoadError:
                raise
            except (
                http.client.HTTPException,
                OSError,
                TimeoutError,
                ssl.SSLError,
            ) as exc:
                last_transport_error = exc
            finally:
                connection.close()
        raise KeyverseProviderLoadError(
            "Keyverse HTTPS transport failed for every pinned address."
        ) from last_transport_error


class KeyverseProviderRegistry:
    """Atomically retain the latest monotonic snapshot for one exact issuer."""

    def __init__(self) -> None:
        """Start empty; callers must load and validate a snapshot before use."""
        self._lock = threading.RLock()
        self._snapshot: KeyverseProviderSnapshot | None = None

    def current(self) -> KeyverseProviderSnapshot:
        """Return the active immutable snapshot or fail before first load."""
        with self._lock:
            if self._snapshot is None:
                raise KeyverseProviderLoadError(
                    "The Keyverse provider snapshot is not loaded."
                )
            return self._snapshot

    def replace(self, snapshot: KeyverseProviderSnapshot) -> None:
        """Replace atomically only with a newer snapshot for the same issuer."""
        with self._lock:
            current = self._snapshot
            if current is not None:
                if snapshot.metadata.issuer != current.metadata.issuer:
                    raise KeyverseProviderLoadError(
                        "A Keyverse provider registry cannot change issuer."
                    )
                if snapshot.loaded_at <= current.loaded_at:
                    raise KeyverseProviderLoadError(
                        "A Keyverse provider refresh must be newer than the active snapshot."
                    )
            self._snapshot = snapshot


def build_openid_configuration_url(issuer: str) -> str:
    """Append the OIDC Discovery suffix after an exact issuer path."""
    _validate_issuer_syntax(issuer)
    return f"{issuer.rstrip('/')}/.well-known/openid-configuration"


def validate_https_endpoint(
    url: str,
    *,
    allowed_hosts: Collection[str],
    resolver: Resolver | None = None,
) -> ValidatedHttpsEndpoint:
    """Validate one closed HTTPS URL, host allowlist, path, and global DNS set."""
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https":
        raise KeyverseProviderLoadError("Keyverse endpoint must use https.")
    if parsed.username is not None or parsed.password is not None:
        raise KeyverseProviderLoadError("Keyverse endpoint must not include userinfo.")
    if parsed.query:
        raise KeyverseProviderLoadError("Keyverse endpoint must not include a query.")
    if parsed.fragment:
        raise KeyverseProviderLoadError("Keyverse endpoint must not include a fragment.")
    if not parsed.hostname:
        raise KeyverseProviderLoadError("Keyverse endpoint must include a host.")
    try:
        parsed_port = parsed.port
        port = 443 if parsed_port is None else parsed_port
    except ValueError as exc:
        raise KeyverseProviderLoadError("Keyverse endpoint port is invalid.") from exc
    if not 1 <= port <= 65535:
        raise KeyverseProviderLoadError("Keyverse endpoint port is invalid.")

    hostname = _normalize_host(parsed.hostname)
    normalized_allowlist = frozenset(
        _normalize_host(host) for host in allowed_hosts if host.strip()
    )
    if hostname not in normalized_allowlist:
        raise KeyverseProviderLoadError(
            "Keyverse endpoint host is not in the allowlist."
        )
    _reject_local_host(hostname)
    request_target = parsed.path or "/"
    _validate_request_path(request_target)
    addresses = _resolve_global_addresses(
        hostname,
        port,
        resolver or _system_resolver,
    )
    normalized_netloc = _format_host_header(hostname, port)
    normalized_url = parsed._replace(netloc=normalized_netloc).geturl()
    return ValidatedHttpsEndpoint(
        url=normalized_url,
        hostname=hostname,
        port=port,
        request_target=request_target,
        host_header=normalized_netloc,
        addresses=addresses,
    )


def load_keyverse_provider(
    settings: KeyverseProviderLoaderSettings,
    *,
    fetcher: KeyverseDocumentFetcher | None = None,
    resolver: Resolver | None = None,
    now: Callable[[], datetime] | None = None,
) -> KeyverseProviderSnapshot:
    """Load, validate, and hash exact OIDC metadata plus its public signing keys."""
    selected_resolver = resolver or _system_resolver
    issuer_host = _normalize_host(urlsplit(settings.issuer).hostname or "")
    discovery_endpoint = validate_https_endpoint(
        build_openid_configuration_url(settings.issuer),
        allowed_hosts=frozenset({issuer_host}),
        resolver=selected_resolver,
    )
    selected_fetcher = fetcher or PinnedHttpsDocumentFetcher(
        timeout_seconds=settings.timeout_seconds
    )
    metadata_document = selected_fetcher.fetch(
        discovery_endpoint,
        settings.metadata_maximum_bytes,
    )
    if len(metadata_document) > settings.metadata_maximum_bytes:
        raise KeyverseProviderLoadError("Keyverse metadata document is too large.")
    metadata = _parse_provider_metadata(
        metadata_document,
        expected_issuer=settings.issuer,
    )
    jwks_endpoint = validate_https_endpoint(
        metadata.jwks_uri,
        allowed_hosts=settings.allowed_jwks_hosts,
        resolver=selected_resolver,
    )
    jwks_document = selected_fetcher.fetch(
        jwks_endpoint,
        settings.jwks_maximum_bytes,
    )
    if len(jwks_document) > settings.jwks_maximum_bytes:
        raise KeyverseProviderLoadError("Keyverse JWK document is too large.")
    try:
        key_set = parse_keyverse_jwks(
            jwks_document,
            maximum_bytes=settings.jwks_maximum_bytes,
        )
    except AccessTokenValidationError as exc:
        raise KeyverseProviderLoadError(
            f"Keyverse JWK set validation failed: {exc}"
        ) from exc
    loaded_at = _aware_utc((now or (lambda: datetime.now(timezone.utc)))())
    return KeyverseProviderSnapshot(
        metadata=metadata,
        key_set=key_set,
        discovery_endpoint=discovery_endpoint,
        jwks_endpoint=jwks_endpoint,
        metadata_sha256=_sha256_reference(metadata_document),
        jwks_sha256=_sha256_reference(jwks_document),
        loaded_at=loaded_at,
    )


def _parse_provider_metadata(
    document: bytes,
    *,
    expected_issuer: str,
) -> KeyverseProviderMetadata:
    """Parse the minimal exact OIDC metadata required by the verifier."""
    try:
        payload = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KeyverseProviderLoadError(
            "Keyverse metadata document is malformed."
        ) from exc
    if not isinstance(payload, dict):
        raise KeyverseProviderLoadError("Keyverse metadata must be a JSON object.")
    issuer = payload.get("issuer")
    if not isinstance(issuer, str) or issuer != expected_issuer:
        raise KeyverseProviderLoadError(
            "Keyverse metadata issuer does not exactly match the configured issuer."
        )
    jwks_uri = payload.get("jwks_uri")
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise KeyverseProviderLoadError("Keyverse metadata needs one jwks_uri.")
    raw_algorithms = payload.get("id_token_signing_alg_values_supported")
    if (
        not isinstance(raw_algorithms, list)
        or not raw_algorithms
        or any(not isinstance(value, str) or not value for value in raw_algorithms)
    ):
        raise KeyverseProviderLoadError(
            "Keyverse metadata signing algorithm list is invalid."
        )
    algorithms = frozenset(raw_algorithms)
    if "RS256" not in algorithms:
        raise KeyverseProviderLoadError(
            "Keyverse metadata must advertise RS256 signing support."
        )
    additional_claims = MappingProxyType(
        {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "issuer",
                "jwks_uri",
                "id_token_signing_alg_values_supported",
            }
        }
    )
    return KeyverseProviderMetadata(
        issuer=issuer,
        jwks_uri=jwks_uri,
        id_token_signing_algorithms=algorithms,
        additional_claims=additional_claims,
    )


def _validate_issuer_syntax(issuer: str) -> None:
    """Require the exact OIDC issuer URL shape before discovery concatenation."""
    parsed = urlsplit(issuer)
    if (
        issuer != issuer.strip()
        or parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Keyverse requires one exact HTTPS issuer URL.")


def _normalize_host(raw_host: str) -> str:
    """Normalize host spelling for exact allowlist comparison."""
    value = raw_host.strip().rstrip(".")
    if not value:
        return ""
    try:
        return value.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise KeyverseProviderLoadError("Keyverse endpoint host is invalid.") from exc


def _reject_local_host(hostname: str) -> None:
    """Reject local naming conventions and non-global IP literals."""
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "internal"
        or hostname.endswith(".internal")
        or hostname.endswith(".local")
    ):
        raise KeyverseProviderLoadError(
            "Keyverse endpoint host must be globally routable."
        )
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not literal.is_global:
        raise KeyverseProviderLoadError(
            "Keyverse endpoint IP must be globally routable."
        )


def _validate_request_path(path: str) -> None:
    """Reject encoded delimiters, traversal, backslashes, and control characters."""
    lower_path = path.casefold()
    if "\\" in path or "%2f" in lower_path or "%5c" in lower_path:
        raise KeyverseProviderLoadError("Keyverse endpoint path is invalid.")
    try:
        decoded = unquote(path, errors="strict")
    except UnicodeError as exc:
        raise KeyverseProviderLoadError("Keyverse endpoint path is invalid.") from exc
    if any(segment in {".", ".."} for segment in decoded.split("/")):
        raise KeyverseProviderLoadError("Keyverse endpoint path is invalid.")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in decoded):
        raise KeyverseProviderLoadError("Keyverse endpoint path is invalid.")


def _resolve_global_addresses(
    hostname: str,
    port: int,
    resolver: Resolver,
) -> tuple[str, ...]:
    """Resolve once, reject any non-global answer, and preserve deterministic order."""
    try:
        raw_addresses = resolver(hostname, port)
    except (OSError, socket.gaierror, KeyError, ValueError) as exc:
        raise KeyverseProviderLoadError(
            "Keyverse endpoint host could not resolve to global addresses."
        ) from exc
    addresses: list[str] = []
    seen: set[str] = set()
    for raw_address in raw_addresses:
        try:
            address = str(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise KeyverseProviderLoadError(
                "Keyverse endpoint resolved address must be globally routable."
            ) from exc
        if not ipaddress.ip_address(address).is_global:
            raise KeyverseProviderLoadError(
                "Keyverse endpoint resolved address must be globally routable."
            )
        if address not in seen:
            seen.add(address)
            addresses.append(address)
    if not addresses:
        raise KeyverseProviderLoadError(
            "Keyverse endpoint host did not resolve to an address."
        )
    return tuple(addresses)


def _system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve TCP addresses using the operating system without opening a socket."""
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(str(info[4][0]) for info in infos)


def _format_host_header(hostname: str, port: int) -> str:
    """Format the original TLS host for HTTP, including explicit non-default ports."""
    try:
        is_ipv6 = ipaddress.ip_address(hostname).version == 6
    except ValueError:
        is_ipv6 = False
    rendered = f"[{hostname}]" if is_ipv6 else hostname
    return rendered if port == 443 else f"{rendered}:{port}"


def _create_pinned_connection(
    address: str,
    port: int,
    hostname: str,
    timeout: float,
) -> _ConnectionLike:
    """Create one TLS connection pinned to an address but verified for the host."""
    return _PinnedHttpsConnection(
        address,
        port=port,
        server_hostname=hostname,
        timeout=timeout,
        context=ssl.create_default_context(),
    )


class _PinnedHttpsConnection(http.client.HTTPSConnection):
    """HTTPS connection that separates the dialed address from TLS host identity."""

    def __init__(
        self,
        address: str,
        *,
        port: int,
        server_hostname: str,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        """Store the original hostname while the base class dials the pinned IP."""
        super().__init__(address, port=port, timeout=timeout, context=context)
        self._server_hostname = server_hostname

    def connect(self) -> None:
        """Dial the pinned IP and verify TLS using the reviewed endpoint hostname."""
        raw_socket = socket.create_connection(
            (self.host, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(
            raw_socket,
            server_hostname=self._server_hostname,
        )


def _sha256_reference(document: bytes) -> str:
    """Return a stable prefixed digest for source and rotation evidence."""
    return f"sha256:{hashlib.sha256(document).hexdigest()}"


def _aware_utc(value: datetime) -> datetime:
    """Require an aware snapshot time and normalize it to UTC."""
    if value.tzinfo is None:
        raise KeyverseProviderLoadError(
            "Keyverse provider snapshot time must be timezone-aware."
        )
    return value.astimezone(timezone.utc)
