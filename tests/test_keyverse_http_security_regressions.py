"""Focused regressions for Keyverse HTTP and browser security boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from cwl_grc.keyverse_authentication import AuthenticatedPrincipal
from cwl_grc.keyverse_http import (
    authenticate_keyverse_request,
    extract_bearer_token,
)
from cwl_grc.officer_console import render_officer_home


NOW = datetime(2026, 8, 31, 12, 20, tzinfo=timezone.utc)


class _PrincipalVerifier:
    """Return one already-verified principal for HTTP-adapter boundary tests."""

    def __init__(self, *, actor_id: str = "officer-park", tenant_id: str = "tenant-acme") -> None:
        self._principal = AuthenticatedPrincipal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            client_id="cwl-grc-web",
            role="compliance_officer",
            workspace_id="grc-primary",
            scopes=frozenset({"grc.policy.read"}),
            token_id="token-boundary-01",
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            principal_kind="human",
        )

    def verify(self, token: str, *, required_scopes=()):  # noqa: ANN001
        """Return the reviewed principal; token cryptography is tested elsewhere."""
        return self._principal


def test_bearer_scheme_is_case_insensitive_without_relaxing_token_spacing() -> None:
    """HTTP auth schemes are case-insensitive while token whitespace stays strict."""
    assert extract_bearer_token("bearer compact-token") == "compact-token"
    assert extract_bearer_token("BeArEr compact-token") == "compact-token"
    for malformed in ("bearer  compact-token", "bearer compact token", "bearer "):
        try:
            extract_bearer_token(malformed)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("malformed Bearer credentials must fail closed")


def test_local_preview_cannot_persist_a_caller_declared_tenant() -> None:
    """Local preview always uses its fixed tenant so CLI and HTTP records stay coherent."""
    principal = authenticate_keyverse_request(
        None,
        authorization=None,
        declared_actor="officer-ahn",
        declared_tenant="tenant-that-does-not-exist-in-preview",
    )
    assert principal.actor_identifier == "officer-ahn"
    assert principal.tenant_identifier == "local_preview"


def test_verified_identity_is_bounded_before_reaching_128_character_columns() -> None:
    """Oversized Keyverse subject and organization claims fail before persistence."""
    for verifier in (
        _PrincipalVerifier(actor_id="a" * 129),
        _PrincipalVerifier(tenant_id="t" * 129),
    ):
        try:
            authenticate_keyverse_request(
                verifier,
                authorization="Bearer reviewed-token",
                declared_actor=None,
            )
        except HTTPException as exc:
            assert exc.status_code == 401
            assert "identity" in str(exc.detail).lower()
        else:
            raise AssertionError("oversized persistent identity must fail closed")


def test_failed_keyverse_reload_clears_stale_protected_browser_state() -> None:
    """A failed replacement token cannot leave the previous officer's state rendered."""
    html = render_officer_home([], keyverse_required=True)
    script = html.split("<script>", 1)[1]
    assert "function resetProtectedState()" in script
    assert "resetProtectedState();" in script
    assert "sessionStorage.removeItem(tokenKey);" in script
    assert "Policy gaps are hidden until Keyverse authorizes this token." in script
