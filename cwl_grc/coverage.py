"""Query controls that still need evidence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cwl_grc.catalog import FrameworkCode
from cwl_grc.models import LOCAL_DEVELOPMENT_TENANT, ControlEvidenceBinding, ControlItem


def list_uncovered_controls(
    session: Session,
    framework: FrameworkCode | None,
    *,
    tenant_id: str = LOCAL_DEVELOPMENT_TENANT,
) -> list[ControlItem]:
    """Return controls without an evidence binding for the exact tenant."""
    bound = select(ControlEvidenceBinding.control_item_id).where(
        ControlEvidenceBinding.tenant_id == tenant_id
    )
    query = session.query(ControlItem).filter(ControlItem.control_item_id.not_in(bound))
    if framework is not None:
        query = query.filter(ControlItem.framework_key == framework.value)
    return list(query.order_by(ControlItem.framework_key, ControlItem.catalog_identifier).all())
