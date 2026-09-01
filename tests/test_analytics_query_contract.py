"""Tests for the versioned GRC Analytics semantic query contract."""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
    QUERY_PLAN_SCHEMA_VERSION,
    READ_MODEL_VERSION,
)

QUESTION_HASH = "a" * 64


def _draft(**changes):
    values = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "analysis_request_id": "analysis-123",
        "question_hash": QUESTION_HASH,
        "dimensions": ("framework", "policy_status"),
        "measures": ("record_count",),
        "filters": (AnalyticsFilter("policy_status", "eq", ("published",)),),
        "time_range": AnalyticsTimeRange(
            "effective_time",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 9, 1, tzinfo=UTC),
        ),
        "row_limit": 100,
    }
    values.update(changes)
    return AnalyticsIntentDraft(**values)


def _context(**changes):
    fields = frozenset(DIMENSION_CODES | MEASURE_CODES)
    values = {
        "principal_identifier": "keyverse:subject-123",
        "tenant_identifier": "tenant-123",
        "workspace_identifier": "workspace-123",
        "purpose_code": "grc.analytics.read",
        "authorization_decision_reference": "authz-123",
        "permitted_fields": fields,
        "available_fields": fields,
    }
    values.update(changes)
    return AnalyticsPlanningContext(**values)


def test_build_query_plan_preserves_verified_scope_without_sql():
    outcome = build_query_plan(_draft(), _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.schema_version == QUERY_PLAN_SCHEMA_VERSION
    assert outcome.read_model_version == READ_MODEL_VERSION
    assert outcome.tenant_identifier == "tenant-123"
    assert outcome.workspace_identifier == "workspace-123"
    assert outcome.principal_identifier == "keyverse:subject-123"
    assert outcome.purpose_code == "grc.analytics.read"
    assert outcome.read_only is True
    assert not hasattr(outcome, "sql")


@pytest.mark.parametrize(
    ("draft", "context", "code", "reason"),
    [
        (
            _draft(analysis_request_id=" unsafe"),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_receipt_identifier",
        ),
        (
            _draft(),
            _context(authorization_decision_reference=""),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_receipt_identifier",
        ),
        (
            _draft(schema_version="future"),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_intent_schema",
        ),
        (
            _draft(question_hash="not-a-hash"),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_question_hash",
        ),
        (
            _draft(measures=()),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "measure_required",
        ),
        (
            _draft(dimensions=("framework", "framework")),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "duplicate_semantic_field",
        ),
        (
            _draft(measures=("record_count", "record_count")),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "duplicate_semantic_field",
        ),
        (
            _draft(dimensions=("secret_table",)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_semantic_field",
        ),
        (
            _draft(measures=("llm_risk_score",)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_semantic_field",
        ),
        (
            _draft(row_limit=0),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "row_limit_out_of_bounds",
        ),
        (
            _draft(row_limit=501),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "row_limit_out_of_bounds",
        ),
        (
            _draft(
                time_range=AnalyticsTimeRange(
                    "created_at", datetime.now(UTC), datetime.now(UTC)
                )
            ),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_time_axis",
        ),
        (
            _draft(
                time_range=AnalyticsTimeRange(
                    "effective_time", datetime(2026, 1, 1), datetime(2026, 2, 1)
                )
            ),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "timezone_required",
        ),
        (
            _draft(
                time_range=AnalyticsTimeRange(
                    "effective_time",
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 2, 1),
                )
            ),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "timezone_required",
        ),
        (
            _draft(
                time_range=AnalyticsTimeRange(
                    "effective_time",
                    datetime(2026, 2, 1, tzinfo=UTC),
                    datetime(2026, 1, 1, tzinfo=UTC),
                )
            ),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_time_range",
        ),
        (
            _draft(filters=(AnalyticsFilter("secret_table", "eq", ("x",)),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_filter_field",
        ),
        (
            _draft(filters=(AnalyticsFilter("policy_status", "contains", ("x",)),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "unsupported_filter_operator",
        ),
        (
            _draft(filters=(AnalyticsFilter("policy_status", "eq", ()),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_filter_value",
        ),
        (
            _draft(filters=(AnalyticsFilter("policy_status", "eq", (" ",)),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_filter_value",
        ),
        (
            _draft(filters=(AnalyticsFilter("policy_status", "eq", ("x" * 257,)),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_filter_value",
        ),
        (
            _draft(filters=(AnalyticsFilter("policy_status", "eq", ("a", "b")),)),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "invalid_equals_cardinality",
        ),
        (
            _draft(
                filters=(
                    AnalyticsFilter("policy_status", "in", tuple(str(i) for i in range(101))),
                )
            ),
            _context(),
            AbstentionCode.UNSUPPORTED_ANALYSIS,
            "filter_cardinality_exceeded",
        ),
        (
            _draft(),
            _context(permitted_fields=frozenset({"framework", "record_count", "effective_time"})),
            AbstentionCode.NOT_AUTHORIZED,
            "field_policy_denied",
        ),
        (
            _draft(),
            _context(available_fields=frozenset({"framework", "record_count", "effective_time"})),
            AbstentionCode.INSUFFICIENT_EVIDENCE,
            "projection_field_unavailable",
        ),
    ],
)
def test_build_query_plan_fails_closed(draft, context, code, reason):
    outcome = build_query_plan(draft, context)

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is code
    assert outcome.reason == reason


def test_filter_in_accepts_bounded_values_and_recorded_time():
    draft = _draft(
        filters=(AnalyticsFilter("framework", "in", ("ISO-27001", "NIST-800-53")),),
        time_range=AnalyticsTimeRange(
            "recorded_time",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
        ),
    )

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.filters == draft.filters
    assert outcome.time_range == draft.time_range


def test_query_plan_can_omit_time_range_without_widening_other_scope():
    draft = _draft(time_range=None)

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.time_range is None


def test_time_range_accepts_utc_forward_interval_across_repeated_local_hour():
    new_york = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 50, tzinfo=new_york, fold=0)
    end = datetime(2026, 11, 1, 1, 10, tzinfo=new_york, fold=1)
    draft = _draft(time_range=AnalyticsTimeRange("effective_time", start, end))

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.time_range == draft.time_range


def test_time_range_rejects_utc_reverse_interval_across_repeated_local_hour():
    new_york = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 10, tzinfo=new_york, fold=1)
    end = datetime(2026, 11, 1, 1, 50, tzinfo=new_york, fold=0)
    draft = _draft(time_range=AnalyticsTimeRange("effective_time", start, end))

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "invalid_time_range"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (
            datetime.min.replace(tzinfo=timezone(timedelta(hours=14))),
            datetime.min.replace(hour=1, tzinfo=timezone(timedelta(hours=14))),
        ),
        (
            datetime.max.replace(hour=22, tzinfo=timezone(-timedelta(hours=14))),
            datetime.max.replace(tzinfo=timezone(-timedelta(hours=14))),
        ),
    ],
)
def test_time_range_accepts_extreme_aware_boundaries_without_utc_overflow(start, end):
    draft = _draft(time_range=AnalyticsTimeRange("effective_time", start, end))

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.time_range == draft.time_range
