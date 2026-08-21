"""Build a truthful, local-only compliance-posture projection."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from cwl_grc.catalog import list_control_items
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.policy import list_policy_gaps


def build_preview_posture(session: Session) -> dict[str, Any]:
    """Return exact local evidence counts without inventing effectiveness truth.

    The current product has an official external-control catalog and legacy
    evidence bindings, but it does not yet own tenant authorization, internal
    control definitions, or effectiveness tests. The projection therefore
    exposes exact-value rows and explicit limitations instead of a compliance
    score or an effective-control claim.
    """
    controls = list_control_items(session, None)
    uncovered = list_uncovered_controls(session, None)
    policy_gaps = list_policy_gaps(session, None)
    uncovered_ids = {item.control_item_id for item in uncovered}
    status_rows: list[dict[str, str]] = []
    for item in controls:
        if item.control_item_id in uncovered_ids:
            status = "not_assessed"
            reason = "No legacy evidence binding is recorded for this catalog item."
        else:
            status = "unknown"
            reason = (
                "Legacy evidence is present, but internal-control implementation and "
                "effectiveness testing are not modeled."
            )
        status_rows.append(
            {
                "framework": item.framework_key,
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
            "status": "not_configured",
            "next_action": (
                "Configure Keyverse-backed identity and tenant authorization before "
                "exposing this projection remotely."
            ),
        },
        "metrics": {
            "official_control_count": len(controls),
            "legacy_evidence_only_count": len(controls) - len(uncovered),
            "not_assessed_control_count": len(uncovered),
            "effective_control_count": 0,
            "policy_gap_count": len(policy_gaps),
        },
        "exact_value_rows": status_rows,
        "next_actions": [
            "Configure Keyverse-backed identity and tenant authorization before remote exposure.",
            "Define internal controls and effectiveness tests before calling a control effective.",
            "Review policy gaps and attach the next evidence where the local preview identifies a gap.",
        ],
        "limitations": [
            "This local preview is not tenant-scoped and is not production authorization evidence.",
            "A legacy evidence binding does not prove internal-control effectiveness.",
            "The zero effective-control count is a deliberate fail-closed boundary, not a certification claim.",
        ],
    }
