"""Regression tests for fail-closed version-one idempotency reservations."""

from __future__ import annotations

from fastapi import HTTPException
import pytest

from cwl_grc.app import _require_idempotency_record
from cwl_grc.models import IdempotencyRecord


def test_idempotency_reservation_guard_returns_confirmed_record() -> None:
    """Preserve the durable record after a successful reservation."""
    record = IdempotencyRecord(
        idempotency_record_id="record-1",
        actor_identifier="officer-v1",
        operation_name="v1_policy_document_create",
        idempotency_key="create-1",
        request_digest="0" * 64,
        response_status=0,
        response_payload="{}",
        created_at=None,
    )

    assert _require_idempotency_record(record) is record


def test_idempotency_reservation_guard_fails_closed_with_next_action() -> None:
    """Do not rely on an optimized-away assert when no reservation exists."""
    with pytest.raises(HTTPException) as missing:
        _require_idempotency_record(None)

    assert missing.value.status_code == 503
    assert missing.value.detail == (
        "The write reservation could not be confirmed. "
        "Retry the same request with the same Idempotency-Key."
    )
