"""Versioned semantic-query contracts for the GRC Analytics bounded context."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

INTENT_SCHEMA_VERSION = "cwl.grc.analytics.intent.v1"
QUERY_PLAN_SCHEMA_VERSION = "cwl.grc.analytics.query-plan.v1"
READ_MODEL_VERSION = "cwl.grc.analytics.read-model.v1"
MAX_RESULT_ROWS = 500
MAX_FILTER_COUNT = 64
MAX_FILTER_VALUES = 100

DIMENSION_CODES = frozenset(
    {
        "framework",
        "framework_edition",
        "obligation",
        "jurisdiction",
        "policy",
        "policy_status",
        "internal_control",
        "control_type",
        "control_frequency",
        "control_owner",
        "control_implementation",
        "system_scope",
        "evidence_source",
        "evidence_period",
        "evidence_freshness",
        "evidence_quality",
        "control_test",
        "control_test_result",
        "control_effectiveness",
        "risk_category",
        "risk_treatment",
        "risk_acceptance",
        "audit_program",
        "audit_engagement",
        "audit_finding",
        "finding_severity",
        "remediation_status",
        "remediation_due_date",
        "remediation_verification",
        "tenant",
        "workspace",
        "effective_time",
        "recorded_time",
    }
)

MEASURE_CODES = frozenset(
    {
        "record_count",
        "evidence_age_days",
        "evidence_record_count",
        "control_test_count",
        "inherent_risk",
        "residual_risk",
        "kri_value",
        "open_finding_count",
        "remediation_item_count",
    }
)


class AbstentionCode(StrEnum):
    """Machine-readable reasons why analysis cannot safely proceed."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_AUTHORIZED = "not_authorized"
    UNSUPPORTED_ANALYSIS = "unsupported_analysis"


class FilterOperator(StrEnum):
    """Operators accepted by the version-one semantic filter contract."""

    EQUALS = "eq"
    IN = "in"


class TimeAxis(StrEnum):
    """Temporal axes supported by the version-one analytics contract."""

    EFFECTIVE_TIME = "effective_time"
    RECORDED_TIME = "recorded_time"


@dataclass(frozen=True, slots=True)
class AnalyticsFilter:
    """One semantic filter expressed without SQL or provider-specific syntax."""

    field: str
    operator: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalyticsTimeRange:
    """A bounded, timezone-aware interval over one explicit temporal axis."""

    axis: str
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class AnalyticsIntentDraft:
    """Untrusted structured intent produced from a natural-language question."""

    schema_version: str
    analysis_request_id: str
    question_hash: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    filters: tuple[AnalyticsFilter, ...] = ()
    time_range: AnalyticsTimeRange | None = None
    row_limit: int = 100


@dataclass(frozen=True, slots=True)
class AnalyticsPlanningContext:
    """Verified identity, tenancy, purpose, and field-policy inputs to planning."""

    principal_identifier: str
    tenant_identifier: str
    workspace_identifier: str
    purpose_code: str
    authorization_decision_reference: str
    permitted_fields: frozenset[str]
    available_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class AnalyticsQueryPlan:
    """Deterministic read-only plan for an allowlisted analytics read model."""

    schema_version: str
    read_model_version: str
    analysis_request_id: str
    question_hash: str
    principal_identifier: str
    tenant_identifier: str
    workspace_identifier: str
    purpose_code: str
    authorization_decision_reference: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    filters: tuple[AnalyticsFilter, ...]
    time_range: AnalyticsTimeRange | None
    row_limit: int
    read_only: bool = field(init=False, default=True)


@dataclass(frozen=True, slots=True)
class AnalyticsAbstention:
    """Typed fail-closed outcome returned instead of guessing or broadening scope."""

    code: AbstentionCode
    reason: str
