"""Exercise privacy request decisions with synthetic unit-test data only."""
from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from cwl_grc.remote_access import PreviewBoundaryMiddleware, request_is_local


def run_request(
    headers: list[tuple[str, str]] | None = None, *, method: str = "POST",
    authority: str | None = "127.0.0.1:8000", client_host: str | None = "127.0.0.1",
    scheme: str = "http", scope_type: str = "http", response_status: int = 201,
) -> tuple[list[Message], list[bytes], list[str]]:
    """Exercise the real ASGI boundary, recording downstream calls and body reads."""
    request_headers = [] if authority is None else [(b"host", authority.encode("latin-1"))]
    request_headers += [(key.encode("latin-1"), value.encode("latin-1")) for key, value in headers or []]
    scope: Scope = {
        "type": scope_type, "method": method, "scheme": scheme,
        "path": "/officer/policy", "query_string": b"", "headers": request_headers,
        "client": None if client_host is None else (client_host, 43210),
        "server": ("127.0.0.1", 8000), "http_version": "1.1",
    }
    messages: list[Message] = []
    bodies: list[bytes] = []
    events: list[str] = []
    body = b'{"evidence_text":"synthetic unit-test content"}'

    async def receive_request() -> Message:
        """Detect premature body consumption."""
        events.append("body_read")
        return {"type": "http.request", "body": body, "more_body": False}

    async def send_response(message: Message) -> None:
        """Retain exact response frames for integrity assertions."""
        messages.append(message)

    async def application_service(current_scope: Scope, receive: Receive, send: Send) -> None:
        """Observe downstream side effects without replacing any security decision."""
        events.append(current_scope["type"])
        if current_scope["type"] != "http":
            return
        bodies.append((await receive())["body"])
        await send({"type": "http.response.start", "status": response_status, "headers": [
            (b"cache-control", b"public, max-age=3600"),
            (b"content-type", b"application/json"),
        ]})
        await send({"type": "http.response.body", "body": body[:10], "more_body": True})
        await send({"type": "http.response.body", "body": body[10:], "more_body": False})

    asyncio.run(PreviewBoundaryMiddleware(application_service)(scope, receive_request, send_response))
    return messages, bodies, events


@pytest.mark.parametrize("headers", [
    [("origin", "https://untrusted.example")], [("origin", "null")], [("origin", "")],
    [("origin", "http://127.0.0.1:8001")], [("origin", "https://127.0.0.1:8000")],
    [("origin", "http://localhost:8000")], [("origin", "http://127.0.0.1:8000/")],
    [("origin", "http://127.0.0.1:8000?")], [("origin", "http://127.0.0.1:8000#")],
    [("origin", "http://user@127.0.0.1:8000")],
    [("origin", "http://127.0.0.1:8000"), ("Origin", "https://untrusted.example")],
    [("sec-fetch-site", "cross-site")], [("sec-fetch-site", "same-site")],
    [("sec-fetch-site", "")], [("sec-fetch-site", "unknown")],
    [("sec-fetch-site", "same-origin"), ("sec-fetch-site", "none")],
    [("referer", "https://untrusted.example/page")], [("referer", "null")],
    [("origin", "http://127.0.0.1:8000"), ("referer", "https://untrusted.example/page")],
    [("referer", "http://127.0.0.1:8000/"), ("referer", "http://127.0.0.1:8000/")],
    [("content-type", "application/x-www-form-urlencoded")],
    [("content-type", "multipart/form-data; boundary=unit_test")], [("content-type", "text/plain")], [],
    [("content-type", "application/json"), ("content-type", "text/plain")],
    [("x-cwl-preview-request", "1"), ("origin", "null")],
    [("x-cwl-preview-request", "1"), ("sec-fetch-site", "cross-site")],
    [("x-cwl-preview-request", "1"), ("x-cwl-preview-request", "1")],
    [("x-cwl-preview-request", "invalid")],
])
def test_bad_context_never_dispatches(headers: list[tuple[str, str]]) -> None:
    """Reject before reading the request body or executing a mutation."""
    messages, bodies, events = run_request(headers)
    assert messages[0]["status"] == 403
    assert bodies == events == []
    returned = b"".join(message.get("body", b"") for message in messages)
    assert b"untrusted.example" not in returned
    assert b"synthetic unit-test" not in returned
    assert dict(messages[0]["headers"])[b"cache-control"] == b"no-store"


@pytest.mark.parametrize("header_name", [
    "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-forwarded-port", "x-real-ip", "via", "X-Forwarded-For",
])
@pytest.mark.parametrize("header_value", ["", " ", "for=198.51.100.23"])
def test_any_proxy_evidence_is_rejected(header_name: str, header_value: str) -> None:
    """Present-empty forwarding is not evidence of direct network access."""
    messages, bodies, events = run_request([(header_name, header_value)])
    assert messages[0]["status"] == 503
    assert bodies == events == []


@pytest.mark.parametrize("authority", [
    None, "", "untrusted.example:8000", "localhost.untrusted.example:8000",
    "127.0.0.1:0", "127.0.0.1:65536", "127.0.0.1:-1", "127.0.0.1:port", "127.0.0.1:",
    "127.0.0.1:8000/", "127.0.0.1:8000?", "127.0.0.1:8000#", "user@127.0.0.1:8000",
    "user:secret@127.0.0.1:8000", "::1", "[::1", "[::1%25lo]:8000", "127.1:8000",
    "2130706433:8000", "127.0.0.1:8000,untrusted.example", "127.0.0.1:8000\\untrusted.example",
    " localhost:8000", "localhost:8000\t", "loc\xe4lhost:8000", "a" * 2049,
])
def test_host_is_literal_and_local(authority: str | None) -> None:
    """Block DNS-controlled authorities and URL parser ambiguity."""
    messages, bodies, events = run_request(method="GET", authority=authority)
    assert messages[0]["status"] == 403
    assert bodies == events == []


@pytest.mark.parametrize("client_host", [None, "198.51.100.23", "not-an-address"])
def test_origin_cannot_authorize_a_remote_peer(client_host: str | None) -> None:
    """A same-origin header cannot replace the direct-peer boundary."""
    messages, bodies, events = run_request([("origin", "http://127.0.0.1:8000")], client_host=client_host)
    assert messages[0]["status"] == 503
    assert bodies == events == []


@pytest.mark.parametrize("headers,method", [
    ([("origin", "http://127.0.0.1:8000")], "POST"),
    ([("origin", "http://127.0.0.1:8000"), ("referer", "http://127.0.0.1:8000/form?view=edit")], "POST"),
    ([("referer", "http://127.0.0.1:8000/form?view=edit")], "POST"),
    ([("sec-fetch-site", "same-origin")], "POST"), ([("x-cwl-preview-request", "1")], "POST"),
    ([("content-type", "application/json")], "POST"),
    ([("content-type", "application/json; charset=utf-8")], "PATCH"),
    ([("sec-fetch-site", "none")], "GET"), ([], "GET"), ([], "HEAD"), ([], "OPTIONS"),
])
def test_intentional_local_use_preserves_bytes(headers: list[tuple[str, str]], method: str) -> None:
    """Do not mask or buffer legitimate policy/evidence request and response data."""
    messages, bodies, events = run_request(headers, method=method)
    assert messages[0]["status"] == 201
    assert events == ["http", "body_read"]
    assert b"".join(message.get("body", b"") for message in messages) == bodies[0]


@pytest.mark.parametrize("authority,origin,scheme,client_host", [
    ("localhost:8000", "http://localhost:8000", "http", "127.0.0.1"),
    ("LOCALHOST", "http://localhost:80", "http", "127.0.0.1"),
    ("127.0.0.1", "https://127.0.0.1:443", "https", "127.0.0.1"),
    ("[::1]:8000", "http://[0:0:0:0:0:0:0:1]:8000", "http", "::1"),
    ("127.0.0.2:8000", "http://127.0.0.2:8000", "http", "127.0.0.1"),
    ("testserver", "http://testserver", "http", "testclient"),
])
def test_exact_origin_normalization(authority: str, origin: str, scheme: str, client_host: str) -> None:
    """Normalize default ports and equivalent IP literals, not distinct origins."""
    messages, _, _ = run_request([("origin", origin)], authority=authority, scheme=scheme, client_host=client_host)
    assert messages[0]["status"] == 201


@pytest.mark.parametrize("status", [200, 303, 400, 401, 403, 404, 422, 500])
def test_response_privacy_headers(status: int) -> None:
    """Protect success, redirect and downstream error responses from retention."""
    messages, _, _ = run_request(method="GET", response_status=status)
    headers = dict(messages[0]["headers"])
    assert headers[b"cache-control"] == b"no-store"
    assert headers[b"pragma"] == b"no-cache"
    assert headers[b"referrer-policy"] == b"same-origin"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]


def test_other_transports_and_ambiguous_host() -> None:
    """Preserve lifespan, reject websocket and deny duplicate/synthetic network hosts."""
    assert run_request(scope_type="lifespan")[2] == ["lifespan"]
    assert run_request(scope_type="websocket") == ([{"type": "websocket.close", "code": 1008}], [], [])
    assert run_request([("Host", "127.0.0.1:8000")], method="GET")[0][0]["status"] == 403
    assert run_request(method="GET", authority="testserver")[0][0]["status"] == 403
    assert run_request(method="GET", scheme="ftp")[0][0]["status"] == 403


@pytest.mark.parametrize("client_host,expected", [
    ("testclient", True), ("localhost", True), ("127.0.0.1", True), ("::1", True),
    ("198.51.100.23", False), ("not-an-address", False), (None, False),
])
def test_legacy_peer_contract(client_host: str | None, expected: bool) -> None:
    """Keep the public peer API while rejecting empty forwarding values."""
    assert request_is_local(client_host, None, None) is expected
    assert request_is_local(client_host, "", None) is False
    assert request_is_local(client_host, None, "") is False


def test_referrer_policy_preserves_native_form_origin() -> None:
    """Fetch Standard nulls native form Origin under no-referrer, breaking local forms."""
    messages, _, _ = run_request(method="GET")
    assert dict(messages[0]["headers"])[b"referrer-policy"] == b"same-origin"
