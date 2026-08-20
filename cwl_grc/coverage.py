"""Project external catalog requirements through reviewed control effectiveness."""

from __future__ import annotations

from sqlalchemy.orm import Session

from cwl_grc.catalog import FrameworkCode
from cwl_grc.internal_controls import (
    ControlCoverage,
    ControlCoverageStatus,
    control_coverage_status,
    list_control_coverage,
)
from cwl_grc.models import LOCAL_DEVELOPMENT_TENANT, ControlItem


def list_uncovered_controls(
    session: Session,
    framework: FrameworkCode | None,
    *,
    tenant_id: str = LOCAL_DEVELOPMENT_TENANT,
) -> list[ControlItem]:
    """Return requirements that are not operating-effective or authorized N/A."""
    return [
        item.control_item
        for item in list_control_coverage(session, framework, tenant_id=tenant_id)
        if item.status
        not in {ControlCoverageStatus.OPERATING_EFFECTIVE, ControlCoverageStatus.NOT_APPLICABLE}
    ]


__all__ = [
    "ControlCoverage",
    "ControlCoverageStatus",
    "control_coverage_status",
    "list_control_coverage",
    "list_uncovered_controls",
]
