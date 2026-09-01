"""Deterministically validate analytics intent and build a read-only query plan."""

from datetime import datetime, timedelta
import re

from cwl_grc.analytics.domain.query_contract import (
    DIMENSION_CODES,
    INTENT_SCHEMA_VERSION,
    MAX_RESULT_ROWS,
    MEASURE_CODES,
    QUERY_PLAN_SCHEMA_VERSION,
    READ_MODEL_VERSION,
    AbstentionCode,
    AnalyticsAbstention,
    AnalyticsFilter,
    AnalyticsIntentDraft,
    AnalyticsPlanningContext,
    AnalyticsQueryPlan,
    AnalyticsTimeRange,
    FilterOperator,
    TimeAxis,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_MICROSECONDS_PER_SECOND = 1_000_000
_SECONDS_PER_DAY = 86_400


def _abstain(code: AbstentionCode, reason: str) -> AnalyticsAbstention:
    """Create a bounded typed abstention without echoing untrusted payloads."""

    return AnalyticsAbstention(code=code, reason=reason)


def _is_safe_identifier(value: str) -> bool:
    """Return whether a receipt identifier is bounded and safe to persist."""

    return bool(_SAFE_IDENTIFIER.fullmatch(value))


def _instant_microseconds(value: datetime, offset: timedelta) -> int:
    """Normalize an aware datetime to an unbounded scalar UTC-instant coordinate."""

    local_seconds = (
        value.toordinal() * _SECONDS_PER_DAY
        + value.hour * 3_600
        + value.minute * 60
        + value.second
    )
    offset_microseconds = (
        (offset.days * _SECONDS_PER_DAY + offset.seconds) * _MICROSECONDS_PER_SECOND
        + offset.microseconds
    )
    return (
        local_seconds * _MICROSECONDS_PER_SECOND
        + value.microsecond
        - offset_microseconds
    )


def _validate_time_range(value: AnalyticsTimeRange | None) -> str | None:
    """Return a stable validation code for an invalid time range, if any."""

    if value is None:
        return None
    if value.axis not in {axis.value for axis in TimeAxis}:
        return "unsupported_time_axis"
    start_offset = value.start.utcoffset()
    end_offset = value.end.utcoffset()
    if start_offset is None or end_offset is None:
        return "timezone_required"
    if _instant_microseconds(value.start, start_offset) >= _instant_microseconds(
        value.end, end_offset
    ):
        return "invalid_time_range"
    return None


def _validate_filter(value: AnalyticsFilter) -> str | None:
    """Return a stable validation code for an invalid semantic filter, if any."""

    if value.field not in DIMENSION_CODES:
        return "unsupported_filter_field"
    if value.operator not in {operator.value for operator in FilterOperator}:
        return "unsupported_filter_operator"
    if not value.values or any(not item.strip() or len(item) > 256 for item in value.values):
        return "invalid_filter_value"
    if value.operator == FilterOperator.EQUALS and len(value.values) != 1:
        return "invalid_equals_cardinality"
    if value.operator == FilterOperator.IN and len(value.values) > 100:
        return "filter_cardinality_exceeded"
    return None


def build_query_plan(
    draft: AnalyticsIntentDraft,
    context: AnalyticsPlanningContext,
) -> AnalyticsQueryPlan | AnalyticsAbstention:
    """Build a deterministic semantic plan or return a typed fail-closed abstention."""

    identifiers = (
        draft.analysis_request_id,
        context.principal_identifier,
        context.tenant_identifier,
        context.workspace_identifier,
        context.purpose_code,
        context.authorization_decision_reference,
    )
    if any(not _is_safe_identifier(value) for value in identifiers):
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "invalid_receipt_identifier")
    if draft.schema_version != INTENT_SCHEMA_VERSION:
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "unsupported_intent_schema")
    if not _SHA256_HEX.fullmatch(draft.question_hash):
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "invalid_question_hash")
    if not draft.measures:
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "measure_required")
    if len(set(draft.dimensions)) != len(draft.dimensions) or len(set(draft.measures)) != len(
        draft.measures
    ):
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "duplicate_semantic_field")

    unsupported_dimensions = set(draft.dimensions) - DIMENSION_CODES
    unsupported_measures = set(draft.measures) - MEASURE_CODES
    if unsupported_dimensions or unsupported_measures:
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "unsupported_semantic_field")
    if not 1 <= draft.row_limit <= MAX_RESULT_ROWS:
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, "row_limit_out_of_bounds")

    time_error = _validate_time_range(draft.time_range)
    if time_error:
        return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, time_error)

    for semantic_filter in draft.filters:
        filter_error = _validate_filter(semantic_filter)
        if filter_error:
            return _abstain(AbstentionCode.UNSUPPORTED_ANALYSIS, filter_error)

    requested_fields = set(draft.dimensions) | set(draft.measures)
    requested_fields.update(semantic_filter.field for semantic_filter in draft.filters)
    if draft.time_range is not None:
        requested_fields.add(draft.time_range.axis)

    if not requested_fields <= context.permitted_fields:
        return _abstain(AbstentionCode.NOT_AUTHORIZED, "field_policy_denied")
    if not requested_fields <= context.available_fields:
        return _abstain(AbstentionCode.INSUFFICIENT_EVIDENCE, "projection_field_unavailable")

    return AnalyticsQueryPlan(
        schema_version=QUERY_PLAN_SCHEMA_VERSION,
        read_model_version=READ_MODEL_VERSION,
        analysis_request_id=draft.analysis_request_id,
        question_hash=draft.question_hash,
        principal_identifier=context.principal_identifier,
        tenant_identifier=context.tenant_identifier,
        workspace_identifier=context.workspace_identifier,
        purpose_code=context.purpose_code,
        authorization_decision_reference=context.authorization_decision_reference,
        dimensions=draft.dimensions,
        measures=draft.measures,
        filters=draft.filters,
        time_range=draft.time_range,
        row_limit=draft.row_limit,
    )
