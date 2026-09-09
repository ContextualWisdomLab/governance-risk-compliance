"""Verify synthetic request-header values do not enter the shared URL parse cache."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest

from cwl_grc.remote_access import normalized_origin, request_rejection_status


@pytest.fixture(autouse=True)
def isolated_url_cache() -> Iterator[None]:
    """Clear synthetic cache entries only in test setup and teardown."""
    urlsplit.cache_clear()
    yield
    urlsplit.cache_clear()


@pytest.mark.parametrize("resource_suffix", [
    "/subject/synthetic_person",
    "?case=synthetic_case",
    "/?token=synthetic_token",
    "/case/synthetic_case?next=https://untrusted.example/private",
    "/synthetic_user@synthetic.example",
    "/subject/%73ynthetic_person?return=%2Fprivate",
])
def test_referer_resource_is_not_cached(resource_suffix: str) -> None:
    """A completed origin check must not retain a raw Referer path or query."""
    source_value = "http://localhost:8000" + resource_suffix
    assert normalized_origin(source_value, allow_resource_path=True) == ("http", "localhost", 8000)
    guard_cache = urlsplit.cache_info()
    urlsplit(source_value)
    probe_cache = urlsplit.cache_info()
    assert probe_cache.hits == guard_cache.hits
    assert probe_cache.misses == guard_cache.misses + 1


@pytest.mark.parametrize("resource_suffix", ["/", "?", "/synthetic_person", "?token=synthetic_token"])
def test_rejected_origin_resource_is_not_cached(resource_suffix: str) -> None:
    """Origin must remain resource-free and rejection must precede shared caching."""
    assert normalized_origin("http://localhost:8000" + resource_suffix) is None
    assert urlsplit.cache_info().currsize == 0


@pytest.mark.parametrize("authority_value", [
    "synthetic_user:synthetic_password@localhost:8000",
    "synthetic_user@localhost:8000",
    "synthetic_user%40synthetic.example@localhost:8000",
    "localhost%25synthetic_secret:8000",
])
@pytest.mark.parametrize("allow_resource_path", [False, True])
def test_rejected_userinfo_never_enters_url_cache(authority_value: str, allow_resource_path: bool) -> None:
    """Reject credentials and encoded authorities before calling the cached parser."""
    assert normalized_origin("http://" + authority_value, allow_resource_path=allow_resource_path) is None
    assert urlsplit.cache_info().currsize == 0


@pytest.mark.parametrize("source_value", ["ftp://localhost/synthetic", "http:/synthetic", "//synthetic"])
def test_invalid_scheme_is_rejected_before_caching(source_value: str) -> None:
    """Unsupported or missing schemes cannot retain arbitrary input in the cache."""
    assert normalized_origin(source_value, allow_resource_path=True) is None
    assert urlsplit.cache_info().currsize == 0


@pytest.mark.parametrize("source_value,expected_origin", [
    ("HTTP://LOCALHOST:80/synthetic", ("http", "localhost", 80)),
    ("https://localhost/synthetic", ("https", "localhost", 443)),
    ("http://[0:0:0:0:0:0:0:1]:8000/synthetic", ("http", "::1", 8000)),
    ("http://127.0.0.1:08000/synthetic", ("http", "127.0.0.1", 8000)),
])
def test_resource_minimization_preserves_origin(source_value: str, expected_origin: tuple[str, str, int]) -> None:
    """Keep supported case, default-port, IPv6 and decimal-port normalization."""
    assert normalized_origin(source_value, allow_resource_path=True) == expected_origin


def test_guard_does_not_clear_other_components_cache() -> None:
    """Avoid replacing minimal parsing with unsafe process-global cache invalidation."""
    unrelated_value = "https://untrusted.example/synthetic_other_component"
    urlsplit(unrelated_value)
    normalized_origin("http://localhost:8000/synthetic_case", allow_resource_path=True)
    guard_cache = urlsplit.cache_info()
    urlsplit(unrelated_value)
    assert urlsplit.cache_info().hits == guard_cache.hits + 1


@pytest.mark.parametrize("referer_value,expected_status", [
    ("http://localhost:8000/subject/synthetic_person?case=synthetic_case", None),
    ("http://localhost:8001/subject/synthetic_person?case=synthetic_case", 403),
    ("http://synthetic_user:synthetic_password@localhost:8000", 403),
])
def test_request_decision_preserves_privacy(referer_value: str, expected_status: int | None) -> None:
    """Exercise the production request decision with local and hostile Referer values."""
    request_scope = {
        "type": "http", "scheme": "http", "method": "POST",
        "client": ("127.0.0.1", 43210),
        "headers": [(b"host", b"localhost:8000"), (b"referer", referer_value.encode("ascii"))],
    }
    assert request_rejection_status(request_scope) == expected_status
    guard_cache = urlsplit.cache_info()
    urlsplit(referer_value)
    assert urlsplit.cache_info().hits == guard_cache.hits
