"""Build a truthful, local-only compliance-posture projection."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from cwl_grc.authorization import PurposeCode
from cwl_grc.catalog import list_control_items
from cwl_grc.models import ControlEvidenceBinding, PolicyDocument
from cwl_grc.policy import list_policy_gaps


def build_preview_posture(
    session: Session,
    *,
    actor_identifier: str,
    tenant_identifier: str,
    purpose_code: PurposeCode,
) -> dict[str, Any]:
    """Return actor-scoped local evidence counts without inventing effectiveness truth.

    The current product has an official external-control catalog and legacy
    evidence bindings, but it does not yet own Keyverse tenant authorization,
    internal control definitions, or effectiveness tests. The projection
    therefore scopes policy gaps and legacy evidence to the declared actor,
    records the declared tenant for audit context, and exposes exact-value
    rows instead of a compliance score.
    """
    controls = list_control_items(session, None)
    actor_bound_ids = _actor_bound_control_ids(session, actor_identifier)
    actor_policy_ids = _actor_policy_ids(session, actor_identifier)
    policy_gaps = [
        gap
        for gap in list_policy_gaps(session, None)
        if gap.policy_document_id in actor_policy_ids
    ]
    status_rows: list[dict[str, str]] = []
    for item in controls:
        if item.control_item_id in actor_bound_ids:
            status = "unknown"
            reason = (
                "Legacy evidence is present for this officer, but internal-control "
                "implementation and effectiveness testing are not modeled."
            )
        else:
            status = "not_assessed"
            reason = (
                "No legacy evidence binding is recorded for this officer on this "
                "catalog item."
            )
        status_rows.append(
            {
                "framework": item.framework_key,
                "catalog_edition": item.control_framework.edition_label,
                "catalog_source_url": item.control_framework.source_url,
                "catalog_identifier": item.catalog_identifier,
                "control_title": item.control_title,
                "status": status,
                "reason": reason,
            }
        )

    return {
        "projection": "workspace_posture",
        "availability": "local_developer_preview",
        "posture_status": "not_assessed",
        "authorization": {
            "status": "declared_preview",
            "tenant_identifier": tenant_identifier,
            "actor_identifier": actor_identifier,
            "purpose_code": purpose_code.value,
            "next_action": (
                "Configure Keyverse-backed identity and tenant authorization before "
                "exposing this projection remotely."
            ),
        },
        "metrics": {
            "official_control_count": len(controls),
            "legacy_evidence_only_count": sum(
                row["status"] == "unknown" for row in status_rows
            ),
            "not_assessed_control_count": sum(
                row["status"] == "not_assessed" for row in status_rows
            ),
            "effective_control_count": 0,
            "policy_gap_count": len(policy_gaps),
        },
        "exact_value_rows": status_rows,
        "policy_gap_rows": [
            {
                "policy_document_id": gap.policy_document_id,
                "policy_title": gap.policy_title,
                "version_number": gap.version_number,
                "framework": gap.framework,
                "catalog_identifier": gap.catalog_identifier,
                "control_title": gap.control_title,
            }
            for gap in policy_gaps
        ],
        "next_actions": [
            "Configure Keyverse-backed identity and tenant authorization before remote exposure.",
            "Define internal controls and effectiveness tests before calling a control effective.",
            "Review policy gaps and attach the next evidence where the local preview identifies a gap.",
        ],
        "limitations": [
            "Actor and tenant values are declarations for this local preview, not Keyverse authentication.",
            "Policy gaps and legacy evidence states are limited to the declared officer.",
            "A legacy evidence binding does not prove internal-control effectiveness.",
            "The zero effective-control count is a deliberate fail-closed boundary, not a certification claim.",
        ],
    }


def _actor_bound_control_ids(session: Session, actor_identifier: str) -> set[str]:
    """Return catalog items this officer bound, excluding other officers' evidence."""
    return {
        control_item_id
        for (control_item_id,) in session.query(ControlEvidenceBinding.control_item_id)
        .filter_by(bound_by_actor=actor_identifier)
        .all()
    }


def _actor_policy_ids(session: Session, actor_identifier: str) -> set[str]:
    """Return policy documents authored by this officer."""
    return {
        policy_document_id
        for (policy_document_id,) in session.query(PolicyDocument.policy_document_id)
        .filter_by(created_by_actor=actor_identifier)
        .all()
    }
