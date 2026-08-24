"""Focused branch regressions for the Keyverse provider transport boundary."""

from __future__ import annotations

from typing import Any

from cwl_grc.keyverse_provider_loader import (
    PinnedHttpsDocumentFetcher,
    ValidatedHttpsEndpoint,
    validate_https_endpoint,
)


class _JsonResponse:
    """Return one bounded successful JSON response with an explicit length."""

    status = 200

    def getheader(self, name: str) -> str | None:
        """Return deterministic response metadata for the requested header."""
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": "2",
        }.get(name)

    def read(self, _amount: int) -> bytes:
        """Return the complete bounded JSON body."""
        return b"{}"


class _SuccessfulConnection:
    """Exercise the standard request contract and record deterministic cleanup."""

    def __init__(self) -> None:
        self.closed = False
        self.request_headers: dict[str, str] | None = None

    def request(
        self,
        method: str,
        target: str,
        *,
        headers: dict[str, str],
    ) -> None:
        """Capture the GET request used for the pinned endpoint."""
        assert method == "GET"
        assert target == "/jwks"
        self.request_headers = headers

    def getresponse(self) -> Any:
        """Return one successful bounded response."""
        return _JsonResponse()

    def close(self) -> None:
        """Record that the fetcher closed the transport."""
        self.closed = True


def test_fetcher_accepts_valid_declared_content_length_and_closes_connection() -> None:
    """A valid Content-Length proceeds to bounded body reading and cleanup."""
    endpoint = ValidatedHttpsEndpoint(
        url="https://keys.example.test/jwks",
        hostname="keys.example.test",
        port=443,
        request_target="/jwks",
        host_header="keys.example.test",
        addresses=("8.8.8.8",),
    )
    connection = _SuccessfulConnection()
    fetcher = PinnedHttpsDocumentFetcher(
        timeout_seconds=5.0,
        connection_factory=lambda *_args: connection,
    )

    assert fetcher.fetch(endpoint, maximum_bytes=128) == b"{}"
    assert connection.request_headers is not None
    assert connection.request_headers["Host"] == "keys.example.test"
    assert connection.closed is True


def test_global_ip_literal_is_allowed_when_explicitly_allowlisted_and_resolved() -> None:
    """A globally routable literal takes the non-rejection branch safely."""
    endpoint = validate_https_endpoint(
        "https://8.8.8.8/jwks",
        allowed_hosts=frozenset({"8.8.8.8"}),
        resolver=lambda _hostname, _port: ("8.8.8.8",),
    )

    assert endpoint.hostname == "8.8.8.8"
    assert endpoint.addresses == ("8.8.8.8",)
