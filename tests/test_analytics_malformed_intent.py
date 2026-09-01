"""Fail-closed runtime-shape tests for untrusted GRC Analytics intent."""

from dataclasses import replace
from datetime import UTC, datetime
from inspect import signature

import pytest

from cwl_grc.analytics import (
    AbstentionCode,
    AnalyticsAbstention,
    AnalyticsFilter,
    AnalyticsIntentDraft,
    AnalyticsPlanningContext,
    AnalyticsQueryPlan,
    AnalyticsTimeRange,
    build_query_plan,
)
from cwl_grc.analytics.domain.query_contract import (
    DIMENSION_CODES,
    INTENT_SCHEMA_VERSION,
    MEASURE_CODES,
)

QUESTION_HASH = "b" * 64


class _HashExplodes(str):
    """Detect whether an oversized untrusted string is hashed before rejection."""

    def __hash__(self):
        raise AssertionError("oversized semantic string was hashed before its length gate")


class _StripExplodes(str):
    """Detect whether an oversized untrusted filter value is copied by strip()."""

    def strip(self, chars=None):
        raise AssertionError("oversized filter value was stripped before its length gate")


def _draft() -> AnalyticsIntentDraft:
    return AnalyticsIntentDraft(
        schema_version=INTENT_SCHEMA_VERSION,
        analysis_request_id="analysis-shape-123",
        question_hash=QUESTION_HASH,
        dimensions=("framework",),
        measures=("record_count",),
        filters=(AnalyticsFilter("framework", "eq", ("ISO-27001",)),),
        time_range=None,
        row_limit=100,
    )


def _context() -> AnalyticsPlanningContext:
    fields = frozenset(DIMENSION_CODES | MEASURE_CODES)
    return AnalyticsPlanningContext(
        principal_identifier="keyverse:subject-shape-123",
        tenant_identifier="tenant-shape-123",
        workspace_identifier="workspace-shape-123",
        purpose_code="grc.analytics.read",
        authorization_decision_reference="authz-shape-123",
        permitted_fields=fields,
        available_fields=fields,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"question_hash": None},
        {"dimensions": None},
        {"dimensions": ("framework", None)},
        {"measures": None},
        {"measures": ("record_count", None)},
        {"filters": None},
        {"filters": (object(),)},
        {"time_range": object()},
        {"row_limit": "100"},
        {"row_limit": True},
    ],
)
def test_malformed_intent_shapes_abstain_instead_of_raising(changes):
    outcome = build_query_plan(replace(_draft(), **changes), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_intent_shape"


def test_non_string_receipt_identifier_abstains_instead_of_raising():
    outcome = build_query_plan(replace(_draft(), analysis_request_id=None), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_receipt_identifier"


@pytest.mark.parametrize(
    "semantic_filter",
    [
        AnalyticsFilter(None, "eq", ("ISO-27001",)),
        AnalyticsFilter("framework", None, ("ISO-27001",)),
        AnalyticsFilter("framework", "eq", None),
        AnalyticsFilter("framework", "eq", ("ISO-27001", None)),
    ],
)
def test_malformed_filter_shapes_abstain_instead_of_raising(semantic_filter):
    outcome = build_query_plan(replace(_draft(), filters=(semantic_filter,)), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_filter_shape"


@pytest.mark.parametrize(
    "time_range",
    [
        AnalyticsTimeRange(
            None,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
        ),
        AnalyticsTimeRange(
            "effective_time",
            "2026-01-01T00:00:00Z",
            datetime(2026, 2, 1, tzinfo=UTC),
        ),
        AnalyticsTimeRange(
            "effective_time",
            datetime(2026, 1, 1, tzinfo=UTC),
            "2026-02-01T00:00:00Z",
        ),
    ],
)
def test_malformed_time_range_shapes_abstain_instead_of_raising(time_range):
    outcome = build_query_plan(replace(_draft(), time_range=time_range), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_time_range_shape"


def test_oversized_semantic_string_is_rejected_before_hashing():
    oversized = _HashExplodes("x" * 257)

    outcome = build_query_plan(replace(_draft(), dimensions=(oversized,)), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "unsupported_semantic_field"


def test_oversized_filter_value_is_rejected_before_strip_copy():
    oversized = _StripExplodes("x" * 257)
    semantic_filter = AnalyticsFilter("framework", "eq", (oversized,))

    outcome = build_query_plan(replace(_draft(), filters=(semantic_filter,)), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_filter_value"


def test_read_only_flag_is_not_a_query_plan_constructor_argument():
    assert "read_only" not in signature(AnalyticsQueryPlan).parameters

    outcome = build_query_plan(_draft(), _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.read_only is True
