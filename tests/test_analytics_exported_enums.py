"""Regression tests for the public enum forms of analytics contract codes."""

from datetime import UTC, datetime

import pytest

from cwl_grc.analytics import (
    AnalyticsFilter,
    AnalyticsIntentDraft,
    AnalyticsPlanningContext,
    AnalyticsQueryPlan,
    AnalyticsTimeRange,
    FilterOperator,
    TimeAxis,
    build_query_plan,
)
from cwl_grc.analytics.domain.query_contract import (
    DIMENSION_CODES,
    INTENT_SCHEMA_VERSION,
    MEASURE_CODES,
)


def _context() -> AnalyticsPlanningContext:
    """Return a fully authorized context for enum-admission regressions."""

    fields = frozenset(DIMENSION_CODES | MEASURE_CODES)
    return AnalyticsPlanningContext(
        principal_identifier="keyverse:enum-regression",
        tenant_identifier="tenant-enum-regression",
        workspace_identifier="workspace-enum-regression",
        purpose_code="grc.analytics.read",
        authorization_decision_reference="authz-enum-regression",
        permitted_fields=fields,
        available_fields=fields,
    )


def _draft(
    *,
    axis: TimeAxis,
    operator: FilterOperator,
) -> AnalyticsIntentDraft:
    """Build a valid intent using only public enum members for typed codes."""

    values = ("published",) if operator is FilterOperator.EQUALS else ("published", "draft")
    return AnalyticsIntentDraft(
        schema_version=INTENT_SCHEMA_VERSION,
        analysis_request_id="analysis-enum-regression",
        question_hash="a" * 64,
        dimensions=("framework", "policy_status"),
        measures=("record_count",),
        filters=(AnalyticsFilter("policy_status", operator, values),),
        time_range=AnalyticsTimeRange(
            axis,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 9, 1, tzinfo=UTC),
        ),
        row_limit=100,
    )


@pytest.mark.parametrize("axis", list(TimeAxis))
@pytest.mark.parametrize("operator", list(FilterOperator))
def test_public_enum_contract_codes_build_valid_query_plans(
    axis: TimeAxis,
    operator: FilterOperator,
) -> None:
    """Public typed contract values must remain valid planner inputs."""

    draft = _draft(axis=axis, operator=operator)

    outcome = build_query_plan(draft, _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert outcome.time_range is not None
    assert outcome.time_range.axis is axis
    assert outcome.filters[0].operator is operator
