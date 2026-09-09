"""Fail-closed network and browser boundary for the local developer preview."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


REMOTE_PREVIEW_DETAIL = (
    "Remote preview is disabled. Configure Keyverse-backed identity and "
    "tenant authorization before exposing CWL GRC."
)
REQUEST_CONTEXT_DETAIL = "The local preview request context is not permitted."
SINGLE_VALUE_HEADERS = (
    "host", "origin", "referer", "sec-fetch-site", "content-type",
    "x-cwl-preview-request",
)


def request_is_local(
    client_host: str | None,
    forwarded_for: str | None,
    forwarded: str | None,
) -> bool:
    """Accept only direct loopback requests with no proxy forwarding evidence."""
    if forwarded_for is not None or forwarded is not None:
        return False
    if client_host in {"localhost", "testclient"}:
        return True
    if client_host is None:
        return False
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False


def normalized_origin(
    source_value: str, *, allow_resource_path: bool = False,
) -> tuple[str, str, int] | None:
    """Parse a bounded HTTP origin without silently repairing ambiguous input."""
    if not source_value or len(source_value) > 2048:
        return None
    if any(ord(character) <= 32 or ord(character) >= 127 for character in source_value):
        return None
    if "\\" in source_value or "#" in source_value:
        return None
    try:
        parsed_value = urlsplit(source_value)
        host_name = parsed_value.hostname
        port_number = parsed_value.port
    except ValueError:
        return None
    if parsed_value.scheme not in {"http", "https"} or not host_name:
        return None
    if parsed_value.username is not None or "%" in host_name or parsed_value.netloc.endswith(":"):
        return None
    if not allow_resource_path and (parsed_value.path or "?" in source_value):
        return None
    if port_number is None:
        port_number = 443 if parsed_value.scheme == "https" else 80
    if not 1 <= port_number <= 65535:
        return None
    try:
        host_name = ip_address(host_name).compressed
    except ValueError:
        host_name = host_name.lower()
    return parsed_value.scheme, host_name, port_number


def authority_is_local(host_name: str, client_host: str | None) -> bool:
    """Accept literal loopback authorities, retaining only the in-process test host."""
    if host_name == "localhost":
        return True
    if host_name == "testserver":
        return client_host == "testclient"
    try:
        return ip_address(host_name).is_loopback
    except ValueError:
        return False


def request_rejection_status(request_scope: Scope) -> int | None:
    """Reject a peer or browser context before any request body or handler is used."""
    request_headers = Headers(raw=[
        (header_name.lower(), header_value)
        for header_name, header_value in request_scope["headers"]
    ])
    client_address = request_scope.get("client")
    client_host = None if client_address is None else client_address[0]
    if not request_is_local(client_host, None, None):
        return 503
    if any(
        header_name in {"forwarded", "x-real-ip", "via"}
        or header_name.startswith("x-forwarded-")
        for header_name in request_headers
    ):
        return 503
    if any(len(request_headers.getlist(header_name)) > 1 for header_name in SINGLE_VALUE_HEADERS):
        return 403
    target_origin = normalized_origin(
        f'{request_scope["scheme"]}://{request_headers.get("host", "")}'
    )
    if target_origin is None or not authority_is_local(target_origin[1], client_host):
        return 403
    fetch_site = request_headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        return 403
    client_marker = request_headers.get("x-cwl-preview-request")
    if client_marker is not None and client_marker != "1":
        return 403
    origin_value = request_headers.get("origin")
    referer_value = request_headers.get("referer")
    if origin_value is not None and normalized_origin(origin_value) != target_origin:
        return 403
    if referer_value is not None and normalized_origin(
        referer_value, allow_resource_path=True,
    ) != target_origin:
        return 403
    if origin_value is not None or referer_value is not None or fetch_site == "same-origin":
        return None
    if request_scope["method"] in {"GET", "HEAD", "OPTIONS"} or client_marker == "1":
        return None
    # Cross-origin browsers must preflight these requests; CORS is not enabled.
    # The marker/content type is CSRF intent evidence, never actor authentication.
    media_type = request_headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        return None
    return 403


class PreviewBoundaryMiddleware:
    """Protect local HTTP requests and emitted responses without buffering payloads."""

    def __init__(self, app: ASGIApp) -> None:
        """Accept the ASGI framework's application argument without storing request state."""
        self.application_service = app

    async def __call__(
        self, request_scope: Scope, receive_message: Receive, send_message: Send,
    ) -> None:
        """Enforce direct local HTTP and preserve lifespan without exposing WebSockets."""
        if request_scope["type"] == "websocket":
            await send_message({"type": "websocket.close", "code": 1008})
            return
        if request_scope["type"] != "http":
            await self.application_service(request_scope, receive_message, send_message)
            return

        async def send_private_response(response_message: Message) -> None:
            """Apply response privacy policy while preserving streaming body frames."""
            if response_message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=response_message)
                response_headers["cache-control"] = "no-store"
                response_headers["pragma"] = "no-cache"
                response_headers["referrer-policy"] = "same-origin"
                response_headers["x-content-type-options"] = "nosniff"
                response_headers["x-frame-options"] = "DENY"
                response_headers.append(
                    "content-security-policy", "frame-ancestors 'none'; form-action 'self'",
                )
            await send_message(response_message)

        rejection_status = request_rejection_status(request_scope)
        if rejection_status is not None:
            rejection_detail = (
                REMOTE_PREVIEW_DETAIL if rejection_status == 503 else REQUEST_CONTEXT_DETAIL
            )
            rejection_response = JSONResponse(
                {"detail": rejection_detail}, status_code=rejection_status,
            )
            await rejection_response(request_scope, receive_message, send_private_response)
            return
        await self.application_service(request_scope, receive_message, send_private_response)
