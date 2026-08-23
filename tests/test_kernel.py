"""Kernel tests for authorization, encryption, seeding, and module entry."""

from __future__ import annotations

from cryptography.fernet import Fernet
import pytest

import cwl_grc.officer_console as officer_console
from cwl_grc import create_app
from cwl_grc.app import officer_declared_actor, officer_declared_purpose
from cwl_grc.authorization import (
    PurposeCode,
    purpose_label,
    require_purpose,
    seed_authorization_purposes,
)
from cwl_grc.catalog import FrameworkCode, framework_label, seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.models import AuthorizationPurpose, ControlItem
from cwl_grc.officer_console import (
    _OFFICER_FRAMEWORKS,
    parse_control_ref,
    render_officer_home,
)


def test_module_factory_returns_app() -> None:
    app = create_app(database_url="sqlite://")
    assert app.title == "CWL GRC"


def test_framework_labels_are_exhaustive() -> None:
    labels = {code: framework_label(code) for code in FrameworkCode}
    assert labels[FrameworkCode.CSAP_2026].startswith("Korea CSAP")
    assert labels[FrameworkCode.SOC2_TSC_2017].startswith("AICPA")
    assert labels[FrameworkCode.ISMS_P_2023].startswith("KISA ISMS-P")
    assert len(labels) == len(FrameworkCode)


def test_seed_is_idempotent_and_keeps_official_identifiers() -> None:
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        seed_authorization_purposes(session)
        count = session.query(ControlItem).count()
        assert count >= 40
        assert session.query(AuthorizationPurpose).count() == len(PurposeCode)
        csap = (
            session.query(ControlItem)
            .filter_by(
                catalog_identifier="10.2.1",
                framework_key=FrameworkCode.CSAP_2026.value,
            )
            .one()
        )
        assert "사용자 등록" in csap.control_title


def test_evidence_cipher_roundtrip_keeps_pii_readable() -> None:
    cipher = EvidenceCipher(Fernet.generate_key().decode("ascii"))
    text = "Officer Bae (seonghobae@me.com) collected the access register."
    token = cipher.encrypt(text)
    assert token != text.encode("utf-8")
    assert cipher.decrypt(token) == text


def test_evidence_cipher_requires_explicit_ephemeral_mode() -> None:
    with pytest.raises(ValueError, match="evidence key"):
        EvidenceCipher(None)
    cipher = EvidenceCipher(None, allow_ephemeral=True)
    assert cipher.decrypt(cipher.encrypt("usable PII")) == "usable PII"


def test_require_purpose_accepts_only_declared_codes() -> None:
    allowed = require_purpose(
        "officer-ahn",
        PurposeCode.EVIDENCE_BINDING.value,
        PurposeCode.EVIDENCE_BINDING,
    )
    assert allowed.actor_identifier == "officer-ahn"
    assert allowed.purpose_code is PurposeCode.EVIDENCE_BINDING
    assert allowed.tenant_identifier == "local_preview"
    named = require_purpose(
        "officer-ahn",
        PurposeCode.EVIDENCE_BINDING.value,
        PurposeCode.EVIDENCE_BINDING,
        tenant_identifier=" tenant-acme ",
    )
    assert named.tenant_identifier == "tenant-acme"


def test_require_purpose_rejects_blank_actor() -> None:
    try:
        require_purpose(
            "",
            PurposeCode.EVIDENCE_BINDING.value,
            PurposeCode.EVIDENCE_BINDING,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("blank actor must be rejected")


def test_purpose_labels_and_empty_officer_home() -> None:
    assert purpose_label(PurposeCode.HEALTH_PROBE) == "Probe service health"
    assert purpose_label(PurposeCode.POLICY_AUTHORING) == (
        "Author or revise a policy"
    )
    html = render_officer_home([])
    assert "Every seeded control in this catalog has evidence" in html
    assert "Buyer" not in (officer_console.__doc__ or "")
    assert "officer home" in (officer_console.__doc__ or "").casefold()
    assert not hasattr(officer_console, "_BUYER_FRAMEWORKS")
    assert _OFFICER_FRAMEWORKS
    assert 'id="keyverse-access-token"' in html
    assert 'type="password"' in html
    assert "sessionStorage" in html
    assert 'headers.Authorization = "Bearer " + token' in html
    assert 'headers["X-Actor-Id"] = actor' in html
    assert "required" not in html.split('id="keyverse-access-token"')[1].split(">")[0]
    assert "policy_authoring" in html
    assert "evidence_binding" in html
    assert "fetch(form.action" in html
    assert "console.log" not in html
    try:
        parse_control_ref("soc2_tsc_2017")
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete control_ref must fail")


def test_officer_declared_actor_ignores_form_identity_when_bearer_present() -> None:
    assert officer_declared_actor("Bearer token", None, "spoofed-officer") is None
    assert (
        officer_declared_actor("Bearer token", "officer-park", "spoofed-officer")
        == "officer-park"
    )
    assert officer_declared_actor(None, "  ", "officer-ahn") == "officer-ahn"
    assert officer_declared_actor("", None, "  ") is None
    assert officer_declared_actor(None, "officer-header", "officer-form") == (
        "officer-header"
    )
    assert officer_declared_actor(None, None, None) is None
    assert officer_declared_purpose(None, PurposeCode.POLICY_AUTHORING) == (
        PurposeCode.POLICY_AUTHORING.value
    )
    assert officer_declared_purpose(
        PurposeCode.EVIDENCE_BINDING.value,
        PurposeCode.EVIDENCE_BINDING,
    ) == PurposeCode.EVIDENCE_BINDING.value


def test_main_binds_only_loopback(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    def fake_run(app, host, port):  # noqa: ANN001
        captured["host"] = host
        captured["port"] = port
        captured["title"] = app.title

    monkeypatch.setattr("cwl_grc.__main__.uvicorn.run", fake_run)
    monkeypatch.setenv("PORT", "9099")
    monkeypatch.setenv(
        "CWL_GRC_EVIDENCE_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    from cwl_grc.__main__ import main

    main()
    assert captured == {
        "host": "127.0.0.1",
        "port": 9099,
        "title": "CWL GRC",
    }


def test_require_purpose_rejects_mismatched_purpose() -> None:
    try:
        require_purpose(
            "officer-ahn",
            PurposeCode.COVERAGE_REVIEW.value,
            PurposeCode.EVIDENCE_BINDING,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("mismatched purpose must be rejected")
