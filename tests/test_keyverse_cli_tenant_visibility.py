"""Hardened CLI reads preserve officer ownership inside the verified tenant."""

from types import SimpleNamespace

from cwl_grc.cli import _owned_policy_documents
from cwl_grc.keyverse_http import RequestPrincipal


def test_hardened_cli_policy_projection_requires_actor_and_tenant_ownership(monkeypatch) -> None:
    """A verified officer sees only policy documents they created in their tenant."""
    documents = [
        SimpleNamespace(
            policy_document_id="same-tenant-colleague",
            tenant_identifier="tenant-acme",
            created_by_actor="officer-lee",
        ),
        SimpleNamespace(
            policy_document_id="same-tenant-self",
            tenant_identifier="tenant-acme",
            created_by_actor="officer-park",
        ),
        SimpleNamespace(
            policy_document_id="foreign-tenant",
            tenant_identifier="tenant-beta",
            created_by_actor="officer-park",
        ),
    ]
    monkeypatch.setattr(
        "cwl_grc.cli.list_policy_documents",
        lambda _session: documents,
    )

    principal = RequestPrincipal("officer-park", "tenant-acme")
    projected = _owned_policy_documents(object(), principal)

    assert [document.policy_document_id for document in projected] == [
        "same-tenant-self",
    ]


def test_preview_policy_projection_remains_unfiltered(monkeypatch) -> None:
    """Developer preview keeps the existing unscoped local listing behavior."""
    documents = [
        SimpleNamespace(
            policy_document_id="first",
            tenant_identifier="tenant-acme",
            created_by_actor="officer-park",
        ),
        SimpleNamespace(
            policy_document_id="second",
            tenant_identifier="tenant-beta",
            created_by_actor="officer-lee",
        ),
    ]
    monkeypatch.setattr(
        "cwl_grc.cli.list_policy_documents",
        lambda _session: documents,
    )

    assert _owned_policy_documents(object(), None) == documents
