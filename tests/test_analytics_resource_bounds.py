"""Resource-bound regressions for untrusted GRC Analytics intents."""

from dataclasses import replace
from hashlib import sha256

import pytest

from cwl_grc.analytics import (
    AbstentionCode,
    AnalyticsAbstention,
    AnalyticsFilter,
    AnalyticsIntentDraft,
    AnalyticsPlanningContext,
    AnalyticsQueryPlan,
    build_query_plan,
)
from cwl_grc.analytics.domain.query_contract import (
    DIMENSION_CODES,
    INTENT_SCHEMA_VERSION,
    MEASURE_CODES,
)


def _draft(filter_count: int = 1) -> AnalyticsIntentDraft:
    """Build an intent whose filters are individually valid but numerous."""

    return AnalyticsIntentDraft(
        schema_version=INTENT_SCHEMA_VERSION,
        analysis_request_id="analysis-filter-bound",
        question_hash=sha256(b"bounded filters").hexdigest(),
        dimensions=("framework",),
        measures=("record_count",),
        filters=tuple(
            AnalyticsFilter("policy_status", "eq", (f"status-{index}",))
            for index in range(filter_count)
        ),
        row_limit=100,
    )


def _context() -> AnalyticsPlanningContext:
    """Authorize every version-one semantic field for the boundary regression."""

    fields = frozenset(DIMENSION_CODES | MEASURE_CODES)
    return AnalyticsPlanningContext(
        principal_identifier="keyverse:subject-filter-bound",
        tenant_identifier="tenant-filter-bound",
        workspace_identifier="workspace-filter-bound",
        purpose_code="grc.analytics.read",
        authorization_decision_reference="authz-filter-bound",
        permitted_fields=fields,
        available_fields=fields,
    )


def test_query_plan_rejects_more_than_sixty_four_filters():
    """Untrusted intents must not allocate or propagate an unbounded filter list."""

    outcome = build_query_plan(_draft(65), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "filter_count_exceeded"


def test_query_plan_accepts_the_sixty_four_filter_boundary():
    """The resource guard must preserve a documented bounded maximum."""

    outcome = build_query_plan(_draft(64), _context())

    assert isinstance(outcome, AnalyticsQueryPlan)
    assert len(outcome.filters) == 64


@pytest.mark.parametrize(
    "changes",
    [
        {"dimensions": ("framework",) * (len(DIMENSION_CODES) + 1)},
        {"measures": ("record_count",) * (len(MEASURE_CODES) + 1)},
    ],
)
def test_query_plan_bounds_semantic_field_collections_before_iteration(changes):
    """Oversized semantic-field tuples fail before duplicate or membership scans."""

    outcome = build_query_plan(replace(_draft(), **changes), _context())

    assert isinstance(outcome, AnalyticsAbstention)
    assert outcome.code is AbstentionCode.UNSUPPORTED_ANALYSIS
    assert outcome.reason == "semantic_field_count_exceeded"
