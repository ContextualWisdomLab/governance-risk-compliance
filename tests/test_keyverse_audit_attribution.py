"""Keyverse audit events record issuer, client, and correlation without raw tokens."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import text

from cwl_grc.app import create_app
from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import (
    AuthorizationDecision,
    DECISION_ALLOW,
    LOCAL_PREVIEW_CLIENT,
    LOCAL_PREVIEW_ISSUER,
    PurposeCode,
    require_purpose,
    seed_authorization_purposes,
)
from cwl_grc.catalog import FrameworkCode, seed_control_catalog
from cwl_grc.correlation import (
    bind_request_correlation,
    current_correlation_reference,
    looks_like_access_token,
    normalize_correlation_reference,
    reset_request_correlation,
)
from cwl_grc.database import create_session_factory
from cwl_grc.models import AuditEvent
from cwl_grc.policy import ControlRef, author_policy
from test_keyverse_http_route_enforcement import (
    CLIENT_ID,
    ISSUER,
    _signing_material,
    _token,
    _verifier,
)


COMPACT_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJvZmZpY2VyLXBhcmsifQ.sig"


def test_correlation_reference_rejects_token_material_and_keeps_exact_ids() -> None:
    """Usable request IDs stay exact; JWT-like and malformed values are replaced."""
    assert normalize_correlation_reference("officer-park-csap-10-2-1") == (
        "officer-park-csap-10-2-1"
    )
    generated = normalize_correlation_reference(COMPACT_JWT)
    assert generated != COMPACT_JWT
    assert not looks_like_access_token(generated)
    assert looks_like_access_token(COMPACT_JWT)
    assert not looks_like_access_token("a.b.c")
    assert len(normalize_correlation_reference("")) == 32
    assert len(normalize_correlation_reference("has space")) == 32
    assert len(normalize_correlation_reference("x" * 129)) == 32
    assert len(normalize_correlation_reference(None)) == 32
    token = bind_request_correlation("bound-request-01")
    try:
        assert current_correlation_reference() == "bound-request-01"
        assert current_correlation_reference() == "bound-request-01"
    finally:
        reset_request_correlation(token)
    unbound = current_correlation_reference()
    assert len(unbound) == 32
    assert current_correlation_reference() == unbound


def test_keyverse_policy_author_audit_records_issuer_client_and_correlation(
    tmp_path: Path,
) -> None:
    """A CSAP 10.2.1 authoring request stores Keyverse attribution, never the bearer."""
    private_key, jwk = _signing_material("key-1")
    verifier = _verifier(jwk)
    token = _token(private_key)
    database = tmp_path / "attributed.sqlite"
    client = TestClient(
        create_app(
            database_url=f"sqlite:///{database}",
            evidence_key=Fernet.generate_key().decode(),
            access_token_verifier=verifier,
        )
    )
    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "policy_authoring",
            "X-Request-ID": "officer-park-csap-10-2-1",
        },
        json={
            "policy_title": "Logical Access Policy",
            "policy_body": "Least privilege for CSAP 10.2.1.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 201
    assert created.headers["x-request-id"] == "officer-park-csap-10-2-1"
    factory = create_session_factory(f"sqlite:///{database}")
    with factory() as session:
        events = session.query(AuditEvent).all()
        assert len(events) == 1
        event = events[0]
        assert event.issuer_identifier == ISSUER
        assert event.client_identifier == CLIENT_ID
        assert event.tenant_identifier == "tenant-acme"
        assert event.actor_identifier == "officer-park"
        assert event.purpose_code == PurposeCode.POLICY_AUTHORING.value
        assert event.decision_outcome == DECISION_ALLOW
        assert event.correlation_reference == "officer-park-csap-10-2-1"
        assert event.action_name == "author_policy"
        dumped = " ".join(
            [
                event.issuer_identifier,
                event.client_identifier,
                event.tenant_identifier,
                event.actor_identifier,
                event.correlation_reference,
                event.decision_outcome,
                event.resource_identifier,
            ]
        )
        assert token not in dumped
        assert COMPACT_JWT not in dumped
        assert "eyJ" not in dumped


def test_local_preview_and_denied_keyverse_requests_do_not_copy_tokens(
    tmp_path: Path,
) -> None:
    """Local preview uses preview issuer/client; 401s do not persist bearer material."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        document = author_policy(
            session,
            require_purpose(
                "officer-park",
                PurposeCode.POLICY_AUTHORING.value,
                PurposeCode.POLICY_AUTHORING,
            ),
            "Preview Access Policy",
            "Local preview still maps CSAP 10.2.1.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        session.commit()
        event = session.query(AuditEvent).one()
        assert document.policy_title == "Preview Access Policy"
        assert event.issuer_identifier == LOCAL_PREVIEW_ISSUER
        assert event.client_identifier == LOCAL_PREVIEW_CLIENT
        assert event.decision_outcome == DECISION_ALLOW
        assert event.correlation_reference
        assert not looks_like_access_token(event.correlation_reference)

    private_key, jwk = _signing_material("key-1")
    database = tmp_path / "denied.sqlite"
    client = TestClient(
        create_app(
            database_url=f"sqlite:///{database}",
            evidence_key=Fernet.generate_key().decode(),
            access_token_verifier=_verifier(jwk),
        )
    )
    denied = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {_token(private_key)}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "policy_authoring",
            "X-Request-ID": COMPACT_JWT,
        },
        json={
            "policy_title": "Rejected",
            "policy_body": "Must not persist the bearer.",
            "control_refs": [],
        },
    )
    assert denied.status_code == 401
    assert denied.headers["x-request-id"] != COMPACT_JWT
    assert not looks_like_access_token(denied.headers["x-request-id"])
    with create_session_factory(f"sqlite:///{database}")() as session:
        assert session.query(AuditEvent).count() == 0
        raw = session.execute(text("SELECT * FROM audit_event")).all()
        assert raw == []


def test_audit_helpers_reject_token_material_and_unknown_outcomes() -> None:
    """Attribution helpers fail closed instead of copying compact JWT material."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        with pytest.raises(ValueError, match="access-token material"):
            record_audit_event(
                session,
                AuthorizationDecision(
                    "officer-park",
                    PurposeCode.POLICY_AUTHORING,
                    correlation_reference=COMPACT_JWT,
                ),
                "author_policy",
                "policy_document",
                "policy-1",
            )
        with pytest.raises(ValueError, match="access-token material"):
            record_audit_event(
                session,
                AuthorizationDecision(
                    COMPACT_JWT,
                    PurposeCode.POLICY_AUTHORING,
                ),
                "author_policy",
                "policy_document",
                "policy-1",
            )
        with pytest.raises(ValueError, match="allow decisions"):
            record_audit_event(
                session,
                AuthorizationDecision(
                    "officer-park",
                    PurposeCode.POLICY_AUTHORING,
                    decision_outcome="deny",
                ),
                "author_policy",
                "policy_document",
                "policy-1",
            )
        with pytest.raises(ValueError, match="access-token material"):
            record_audit_event(
                session,
                AuthorizationDecision(
                    "",
                    PurposeCode.POLICY_AUTHORING,
                ),
                "author_policy",
                "policy_document",
                "policy-1",
            )
        with pytest.raises(ValueError, match="access-token material"):
            record_audit_event(
                session,
                AuthorizationDecision(
                    " officer-park ",
                    PurposeCode.POLICY_AUTHORING,
                ),
                "author_policy",
                "policy_document",
                "policy-1",
            )
        recorded = record_audit_event(
            session,
            AuthorizationDecision(
                "officer-park",
                PurposeCode.POLICY_AUTHORING,
                correlation_reference="",
                decision_outcome=" ",
            ),
            "author_policy",
            "policy_document",
            "policy-1",
        )
        assert recorded.decision_outcome == DECISION_ALLOW
        assert recorded.correlation_reference


def test_officer_evidence_form_authenticates_before_catalog_validation() -> None:
    """Keyverse officer evidence posts fail closed before catalog well-formedness."""
    _private_key, jwk = _signing_material("key-1")
    client = TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=_verifier(jwk),
        )
    )
    missing = client.post(
        "/officer/evidence",
        data={
            "evidence_title": "CSAP 10.2.1 register",
            "payload_text": "Must authenticate first.",
            "control_ref": "not-a-control",
        },
        follow_redirects=False,
    )
    assert missing.status_code == 401


def test_malformed_bearer_token_is_unauthorized() -> None:
    """A Bearer value that is not a Keyverse access token fails closed with 401."""
    _private_key, jwk = _signing_material("key-1")
    client = TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=_verifier(jwk),
        )
    )
    malformed = client.post(
        "/policy-documents",
        headers={
            "Authorization": "Bearer not-a-keyverse-token",
            "X-Purpose": "policy_authoring",
        },
        json={"policy_title": "X", "policy_body": "Y", "control_refs": []},
    )
    assert malformed.status_code == 401
