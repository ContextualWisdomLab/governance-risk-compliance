"""Strict request models for the audit-management HTTP surface."""

from __future__ import annotations

from datetime import date
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, StringConstraints,
)

from cwl_grc.catalog import FrameworkCode

MAX_POPULATION_SIZE = 1_000_000
"""Largest supported sampling population."""

MAX_EXPECTED_REVISION = 2**31 - 2
"""Largest revision token whose increment fits SQL INTEGER on all supported stores."""

MAX_SAMPLE_SIZE = 10_000
"""Largest sample or full-population test stored in one procedure."""

MIN_SELECTION_SEED = -(2**63)
"""Inclusive signed database BIGINT lower bound for selection seeds."""

MAX_SELECTION_SEED = 2**63 - 1
"""Inclusive signed database BIGINT upper bound for selection seeds."""

StatedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Required free text: surrounding whitespace is stripped and blank text is rejected."""

SeverityRating = Literal["low", "medium", "high", "critical"]
"""Finding severity ratings accepted by the audit_finding_revision table."""

SelectionMethod = Literal["seeded_random", "judgmental", "full_population"]
"""Sample selection methods accepted by the audit_procedure table."""


def _calendar_date(value: object) -> date:
    """Accept only calendar-date objects or exact ISO dates, never Unix timestamps."""
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Use a calendar date in YYYY-MM-DD format.")


CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]
"""Calendar-only date input matching the public date schema."""


class StrictRequest(BaseModel):
    """Base request that rejects undeclared fields such as smuggled tenant identifiers."""

    model_config = ConfigDict(extra="forbid")


class AuditProgramRequest(StrictRequest):
    """Plan one risk-based audit program for a period."""

    program_title: StatedText
    period_start: CalendarDate
    period_end: CalendarDate
    risk_rationale: StatedText
    audit_authority_actor: StatedText


class AuditEngagementRequest(StrictRequest):
    """Plan one engagement under an approved audit program."""

    engagement_title: StatedText
    scope_statement: StatedText
    period_start: CalendarDate
    period_end: CalendarDate
    lead_auditor_actor: StatedText


class EngagementCriterionRequest(StrictRequest):
    """Name one official catalog control as an audit criterion."""

    framework: FrameworkCode
    catalog_identifier: StatedText
    internal_control_reference: StatedText | None = None


class TeamMemberRequest(StrictRequest):
    """Assign one competent auditor to an engagement team."""

    auditor_actor: StatedText
    team_role: Literal["lead", "auditor", "supervisor"]
    competence_statement: StatedText


class IndependenceDeclarationRequest(StrictRequest):
    """Declare whether the requesting auditor has a conflict of interest."""

    has_conflict: StrictBool
    declaration_statement: StatedText


class AuditProcedureRequest(StrictRequest):
    """Document one procedure and its reproducible sample selection."""

    engagement_criterion_id: StatedText
    procedure_description: StatedText
    population_description: StatedText
    population_size: StrictInt = Field(gt=0, le=MAX_POPULATION_SIZE)
    selection_method: SelectionMethod
    sample_size: StrictInt = Field(gt=0, le=MAX_SAMPLE_SIZE)
    selection_seed: StrictInt | None = Field(
        default=None, ge=MIN_SELECTION_SEED, le=MAX_SELECTION_SEED
    )
    selected_ordinals: list[StrictInt] | None = Field(default=None, max_length=MAX_SAMPLE_SIZE)


class EvidenceLinkRequest(StrictRequest):
    """Reference an existing evidence record from a procedure or one sample item."""

    evidence_record_id: StatedText
    population_ordinal: StrictInt | None = Field(default=None, ge=1, le=MAX_POPULATION_SIZE)


class FindingContent(StrictRequest):
    """Shared content of one finding edition."""

    engagement_criterion_id: StatedText
    condition_statement: StatedText
    cause_statement: StatedText
    effect_statement: StatedText
    severity_rating: SeverityRating
    rating_rationale: StatedText
    recommendation_text: StatedText


class FindingIssueRequest(FindingContent):
    """Issue a new finding with an independent remediation owner."""

    remediation_owner_actor: StatedText
    target_date: CalendarDate


class FindingRevisionRequest(FindingContent):
    """Append the next finding edition while holding the current revision number."""

    expected_revision: StrictInt = Field(ge=1, le=MAX_EXPECTED_REVISION)


class RemediationActionRequest(StrictRequest):
    """Record one remediation action for a finding."""

    action_description: StatedText
    owner_actor: StatedText
    due_date: CalendarDate


class ActionCompletionRequest(StrictRequest):
    """Complete a remediation action with an existing evidence record."""

    completion_evidence_record_id: StatedText


class FindingRetestRequest(StrictRequest):
    """Record one independent retest of a finding's remediation."""

    procedure_description: StatedText
    retest_result: Literal["passed", "failed"]
    effectiveness_conclusion: StatedText
    evidence_record_id: StatedText


class FindingClosureRequest(StrictRequest):
    """Close a finding on a passing retest or a bounded risk acceptance."""

    closure_basis: Literal["retest_passed", "risk_accepted"]
    closure_rationale: StatedText
    acceptance_authority_actor: StatedText | None = None
    acceptance_expires_on: CalendarDate | None = None
