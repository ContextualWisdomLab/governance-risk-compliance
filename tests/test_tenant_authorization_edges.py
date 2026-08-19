"""Edge contracts for tenant-bound authorization decisions."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from cwl_grc.authorization import PurposeCode, require_purpose


def test_purpose_decision_rejects_missing_tenant_context() -> None:
    """A resolved actor and purpose cannot proceed without one exact tenant."""
    with pytest.raises(HTTPException) as failure:
        require_purpose(
            "officer-tenant-a",
            PurposeCode.POLICY_AUTHORING.value,
            PurposeCode.POLICY_AUTHORING,
            tenant_id="",
        )
    assert failure.value.status_code == 401
