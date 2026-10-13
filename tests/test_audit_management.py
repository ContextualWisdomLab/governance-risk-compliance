"""Officer workflow tests for audit programs, engagements, findings, and closure."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from cwl_grc import create_app
from cwl_grc.audit_management import (
    AuditWorkflowError,
    list_overdue_remediation,
    select_sample_ordinals,
)
from cwl_grc.authorization import PurposeCode, purpose_label
from cwl_grc.database import create_session_factory
from cwl_grc.migrations import (
    AUDIT_MANAGEMENT_MIGRATION,
    POLICY_INTEGRITY_MIGRATION,
    apply_schema_migrations,
    integrity_guard_statements,
)
from cwl_grc.models import (
    AuditEngagement,
    AuditEvent,
    AuditEvidenceLink,
    AuditFinding,
    AuditProgram,
    RemediationAction,
)


AUTHORITY = "cae-kim"
PLANNER = "audit-planner-lee"
LEAD = "lead-auditor-park"
AUDITOR = "it-auditor-choi"
SUPERVISOR = "audit-supervisor-jung"
OWNER = "iam-owner-han"
ENGINEER = "iam-engineer-yoon"
RISK_AUTHORITY = "ciso-oh"

SEED = 20260701
EXPECTED_SAMPLE = [
    3, 12, 20, 31, 34, 39, 43, 50, 61, 62, 67, 68, 103,
    108, 128, 140, 145, 148, 150, 157, 181, 195, 202, 215, 223,
]


def h(actor: str, purpose: str = "audit_engagement") -> dict[str, str]:
    """Return declared actor and purpose headers."""
    return {"X-Actor-Id": actor, "X-Purpose": purpose}


def _client() -> TestClient:
    """Return a client for an isolated in-memory product."""
    return TestClient(create_app(database_url="sqlite://", evidence_key=None))


def _ok(response, status: int = 201) -> dict:  # noqa: ANN001
    """Assert a status and that the response states the next action."""
    assert response.status_code == status, response.text
    body = response.json()
    assert body["next_action"]
    return body


def _fail(response, status: int) -> dict:  # noqa: ANN001
    """Assert a rejection that still states the next action."""
    assert response.status_code == status, response.text
    body = response.json()
    assert body["next_action"]
    return body


def _evidence(client: TestClient, title: str = "Q3 IAM access review export") -> str:
    """Store one evidence record through the existing evidence route."""
    response = client.post(
        "/evidence-records",
        headers=h("evidence-collector-seo", "evidence_binding"),
        json={"evidence_title": title, "payload_text": f"{title}: 240 accounts reviewed."},
    )
    assert response.status_code == 201
    return response.json()["evidence_record_id"]


def _program(client: TestClient, *, approve: bool = True) -> str:
    """Plan an audit program and optionally have the authority approve it."""
    body = _ok(
        client.post(
            "/audit-programs",
            headers=h(PLANNER),
            json={
                "program_title": "2026 information security internal audit program",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "risk_rationale": "Privileged cloud access is the top-rated ISMS-P risk.",
                "audit_authority_actor": AUTHORITY,
            },
        )
    )
    assert body["program_status"] == "draft"
    if approve:
        approved = _ok(
            client.post(f"/audit-programs/{body['audit_program_id']}/approval", headers=h(AUTHORITY)),
            200,
        )
        assert approved["program_status"] == "approved"
        assert approved["approved_by_actor"] == AUTHORITY
    return body["audit_program_id"]


def _engagement(client: TestClient, program_id: str, **overrides: str) -> str:
    """Create a Q3 access-review engagement under an approved program."""
    payload = {
        "engagement_title": "ISMS-P 2.5.1 user account access review Q3",
        "scope_statement": "Cloud console and IdP accounts for production systems.",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "lead_auditor_actor": LEAD,
    }
    payload.update(overrides)
    body = _ok(
        client.post(f"/audit-programs/{program_id}/engagements", headers=h(AUTHORITY), json=payload)
    )
    assert body["engagement_status"] == "planned"
    return body["audit_engagement_id"]


def _criterion(
    client: TestClient,
    engagement_id: str,
    framework: str = "isms_p_2023",
    identifier: str = "2.5.1",
) -> str:
    """Add one official catalog control as an audit criterion."""
    body = _ok(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(LEAD),
            json={"framework": framework, "catalog_identifier": identifier},
        )
    )
    return body["engagement_criterion_id"]


def _member(client: TestClient, engagement_id: str, actor: str, role: str) -> None:
    """Add one competent team member."""
    _ok(
        client.post(
            f"/audit-engagements/{engagement_id}/team-members",
            headers=h(AUTHORITY),
            json={
                "auditor_actor": actor,
                "team_role": role,
                "competence_statement": "CISA; three prior IAM access-review engagements.",
            },
        )
    )


def _declare(client: TestClient, engagement_id: str, actor: str, conflict: bool = False) -> None:
    """Record one auditor's independence declaration."""
    _ok(
        client.post(
            f"/audit-engagements/{engagement_id}/independence-declarations",
            headers=h(actor),
            json={
                "has_conflict": conflict,
                "declaration_statement": "No IAM operating duties in the audit period.",
            },
        )
    )


def _ready(client: TestClient) -> dict[str, str]:
    """Return a planned engagement with criteria and an independent team."""
    program_id = _program(client)
    engagement_id = _engagement(client, program_id)
    criterion_id = _criterion(client, engagement_id)
    for actor, role in ((LEAD, "lead"), (AUDITOR, "auditor"), (SUPERVISOR, "supervisor")):
        _member(client, engagement_id, actor, role)
        _declare(client, engagement_id, actor)
    return {"program": program_id, "engagement": engagement_id, "criterion": criterion_id}


def _fieldwork(client: TestClient) -> dict[str, str]:
    """Return an engagement that has started fieldwork."""
    ids = _ready(client)
    body = _ok(client.post(f"/audit-engagements/{ids['engagement']}/start", headers=h(LEAD)), 200)
    assert body["engagement_status"] == "fieldwork"
    return ids


def _procedure(client: TestClient, ids: dict[str, str], **overrides: object) -> dict:
    """Document a seeded-random sampling procedure."""
    payload: dict[str, object] = {
        "engagement_criterion_id": ids["criterion"],
        "procedure_description": "Reperform quarterly access recertification for sampled accounts.",
        "population_description": "IdP account register export 2026-09-30, 240 active accounts.",
        "population_size": 240,
        "selection_method": "seeded_random",
        "sample_size": 25,
        "selection_seed": SEED,
    }
    payload.update(overrides)
    return client.post(
        f"/audit-engagements/{ids['engagement']}/procedures",
        headers=h(AUDITOR),
        json=payload,
    )


def _finding_payload(ids: dict[str, str], **overrides: object) -> dict[str, object]:
    """Return a realistic access-review finding."""
    payload: dict[str, object] = {
        "engagement_criterion_id": ids["criterion"],
        "condition_statement": "3 of 25 sampled leavers kept console access past 30 days.",
        "cause_statement": "HR termination feed does not trigger IdP deprovisioning.",
        "effect_statement": "Former staff could access production consoles.",
        "severity_rating": "high",
        "rating_rationale": "Production write access; exploitation needs no further credential.",
        "recommendation_text": "Automate deprovisioning from the HR termination event.",
        "remediation_owner_actor": OWNER,
        "target_date": "2026-11-30",
    }
    payload.update(overrides)
    return payload


def _finding(client: TestClient, ids: dict[str, str], **overrides: object) -> str:
    """Issue one finding during fieldwork."""
    body = _ok(
        client.post(
            f"/audit-engagements/{ids['engagement']}/findings",
            headers=h(AUDITOR),
            json=_finding_payload(ids, **overrides),
        )
    )
    assert body["finding_status"] == "open"
    assert body["current_revision_number"] == 1
    return body["audit_finding_id"]


def _action(client: TestClient, finding_id: str, owner: str = ENGINEER, due: str = "2026-10-31") -> str:
    """Record one remediation action by the remediation owner."""
    body = _ok(
        client.post(
            f"/audit-findings/{finding_id}/remediation-actions",
            headers=h(OWNER, "remediation_tracking"),
            json={
                "action_description": "Wire HR termination webhook to IdP deprovisioning.",
                "owner_actor": owner,
                "due_date": due,
            },
        )
    )
    assert body["action_status"] == "open"
    return body["remediation_action_id"]


def _complete(client: TestClient, action_id: str, evidence_id: str, actor: str = ENGINEER):  # noqa: ANN202
    """Complete one remediation action with evidence."""
    return client.post(
        f"/remediation-actions/{action_id}/completion",
        headers=h(actor, "remediation_tracking"),
        json={"completion_evidence_record_id": evidence_id},
    )


def _retest(client: TestClient, finding_id: str, evidence_id: str, result: str, actor: str = AUDITOR):  # noqa: ANN202
    """Record one independent retest."""
    return client.post(
        f"/audit-findings/{finding_id}/retests",
        headers=h(actor),
        json={
            "procedure_description": "Reperform leaver sample of 10 after webhook go-live.",
            "retest_result": result,
            "effectiveness_conclusion": "Leavers were deprovisioned within one business day.",
            "evidence_record_id": evidence_id,
        },
    )


def _remediated(client: TestClient) -> dict[str, str]:
    """Return a finding whose only action is completed."""
    ids = _fieldwork(client)
    ids["finding"] = _finding(client, ids)
    ids["action"] = _action(client, ids["finding"])
    ids["evidence"] = _evidence(client)
    _ok(_complete(client, ids["action"], ids["evidence"]), 200)
    return ids


def _events(client: TestClient) -> list[str]:
    """Return recorded audit_event action names."""
    with client.app.state.session_factory() as session:
        return [row[0] for row in session.query(AuditEvent.action_name).all()]


def test_isms_p_access_review_runs_from_program_to_closed_engagement() -> None:
    """Verify the ISMS-P audit lifecycle, revision history, evidence links, and audit events."""
    client = _client()
    ids = _fieldwork(client)

    procedure = _ok(_procedure(client, ids))
    assert procedure["selected_ordinals"] == EXPECTED_SAMPLE
    assert procedure["selection_seed"] == SEED
    evidence_id = _evidence(client)
    link = _ok(
        client.post(
            f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": evidence_id},
        )
    )
    assert link["audit_procedure_id"] == procedure["audit_procedure_id"]
    sample_link = _ok(
        client.post(
            f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": evidence_id, "population_ordinal": 43},
        )
    )
    assert sample_link["audit_sample_item_id"]
    assert sample_link["audit_procedure_id"] is None

    finding_id = _finding(client, ids)
    revised = _ok(
        client.post(
            f"/audit-findings/{finding_id}/revisions",
            headers=h(LEAD),
            json={
                "expected_revision": 1,
                **{
                    key: value
                    for key, value in _finding_payload(ids, severity_rating="critical").items()
                    if key not in {"remediation_owner_actor", "target_date"}
                },
            },
        )
    )
    assert revised["current_revision_number"] == 2
    stale = client.post(
        f"/audit-findings/{finding_id}/revisions",
        headers=h(LEAD),
        json={
            "expected_revision": 1,
            **{
                key: value
                for key, value in _finding_payload(ids).items()
                if key not in {"remediation_owner_actor", "target_date"}
            },
        },
    )
    _fail(stale, 409)

    action_id = _action(client, finding_id)
    completed = _ok(_complete(client, action_id, evidence_id), 200)
    assert completed["action_status"] == "completed"
    retest = _ok(_retest(client, finding_id, evidence_id, "passed"))
    assert retest["retest_result"] == "passed"
    closure = _ok(
        client.post(
            f"/audit-findings/{finding_id}/closure",
            headers=h(LEAD),
            json={"closure_basis": "retest_passed", "closure_rationale": "Retest passed."},
        )
    )
    assert closure["finding_status"] == "closed"
    assert closure["finding_retest_id"] == retest["finding_retest_id"]

    history = _ok(client.get(f"/audit-findings/{finding_id}", headers=h(SUPERVISOR)), 200)
    assert [rev["revision_number"] for rev in history["revisions"]] == [1, 2]
    assert [rev["severity_rating"] for rev in history["revisions"]] == ["high", "critical"]
    assert history["revisions"][0]["revised_by_actor"] == AUDITOR
    assert history["remediation_actions"][0]["completion_evidence_record_id"] == evidence_id
    assert history["retests"][0]["retest_actor"] == AUDITOR
    assert history["closure"]["closure_basis"] == "retest_passed"
    assert history["criterion"] == {"framework": "isms_p_2023", "catalog_identifier": "2.5.1"}

    reporting = _ok(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 200)
    assert reporting["engagement_status"] == "reporting"
    closed = _ok(client.post(f"/audit-engagements/{ids['engagement']}/closure", headers=h(LEAD)), 200)
    assert closed["engagement_status"] == "closed"

    view = _ok(client.get(f"/audit-engagements/{ids['engagement']}", headers=h(AUTHORITY)), 200)
    assert view["criteria"][0]["catalog_identifier"] == "2.5.1"
    assert {member["team_role"] for member in view["team_members"]} == {"lead", "auditor", "supervisor"}
    assert len(view["independence_declarations"]) == 3
    assert view["procedures"][0]["selected_ordinals"] == EXPECTED_SAMPLE
    assert len(view["procedures"][0]["evidence_links"]) == 2
    assert view["findings"][0]["finding_status"] == "closed"

    events = _events(client)
    for name in (
        "create_audit_program",
        "approve_audit_program",
        "create_audit_engagement",
        "add_engagement_criterion",
        "add_engagement_team_member",
        "declare_independence",
        "start_audit_engagement",
        "create_audit_procedure",
        "link_audit_evidence",
        "issue_audit_finding",
        "revise_audit_finding",
        "create_remediation_action",
        "complete_remediation_action",
        "record_finding_retest",
        "close_audit_finding",
        "move_engagement_to_reporting",
        "close_audit_engagement",
    ):
        assert name in events
    with client.app.state.session_factory() as session:
        assert session.query(AuditEvidenceLink).count() == 2


def test_audit_tables_never_store_evidence_plaintext() -> None:
    """Verify populated audit tables reference evidence without copying its plaintext."""
    client = _client()
    ids = _remediated(client)
    procedure_id = _ok(_procedure(client, ids))["audit_procedure_id"]
    _ok(
        client.post(
            f"/audit-procedures/{procedure_id}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": ids["evidence"]},
        )
    )
    _ok(_retest(client, ids["finding"], ids["evidence"], "passed"))
    with client.app.state.session_factory() as session:
        for table in ("audit_evidence_link", "remediation_action", "finding_retest", "audit_sample_item"):
            rows = session.execute(text(f"SELECT * FROM {table}")).all()
            assert rows
            assert all("240 accounts reviewed" not in str(row) for row in rows)


def test_program_approval_separates_authority_from_creator() -> None:
    """Reject self-approval, wrong authorities, and engagement creation before approval."""
    client = _client()
    self_planned = _ok(
        client.post(
            "/audit-programs",
            headers=h(AUTHORITY),
            json={
                "program_title": "Self-planned program",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "risk_rationale": "Annual cycle.",
                "audit_authority_actor": AUTHORITY,
            },
        )
    )
    _fail(client.post(f"/audit-programs/{self_planned['audit_program_id']}/approval", headers=h(AUTHORITY)), 403)
    program_id = _program(client, approve=False)
    _fail(client.post(f"/audit-programs/{program_id}/approval", headers=h(LEAD)), 403)
    payload = {
        "engagement_title": "Early engagement",
        "scope_statement": "IdP accounts.",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "lead_auditor_actor": LEAD,
    }
    _fail(client.post(f"/audit-programs/{program_id}/engagements", headers=h(AUTHORITY), json=payload), 409)
    _ok(client.post(f"/audit-programs/{program_id}/approval", headers=h(AUTHORITY)), 200)
    _fail(client.post(f"/audit-programs/{program_id}/approval", headers=h(AUTHORITY)), 409)
    _fail(client.post(f"/audit-programs/{program_id}/engagements", headers=h(LEAD), json=payload), 403)


def test_program_and_engagement_periods_are_validated() -> None:
    """Reject reversed program dates and engagement periods outside the approved program."""
    client = _client()
    reversed_program = client.post(
        "/audit-programs",
        headers=h(PLANNER),
        json={
            "program_title": "Reversed",
            "period_start": "2026-12-31",
            "period_end": "2026-01-01",
            "risk_rationale": "Annual cycle.",
            "audit_authority_actor": AUTHORITY,
        },
    )
    _fail(reversed_program, 400)
    program_id = _program(client)
    for start, end in (("2025-12-01", "2026-02-01"), ("2026-11-01", "2027-01-31"), ("2026-09-30", "2026-07-01")):
        response = client.post(
            f"/audit-programs/{program_id}/engagements",
            headers=h(AUTHORITY),
            json={
                "engagement_title": "Out of period",
                "scope_statement": "IdP accounts.",
                "period_start": start,
                "period_end": end,
                "lead_auditor_actor": LEAD,
            },
        )
        _fail(response, 400)


def _start_missing(client: TestClient, gap: str) -> dict:
    """Build a planned engagement missing exactly one start prerequisite."""
    program_id = _program(client)
    engagement_id = _engagement(client, program_id)
    if gap != "criterion":
        _criterion(client, engagement_id)
    team = {"lead": (LEAD, "lead"), "auditor": (AUDITOR, "auditor"), "supervisor": (SUPERVISOR, "supervisor")}
    if gap == "supervisor":
        team.pop("supervisor")
    if gap == "lead":
        team.pop("lead")
    if gap == "lead_mismatch":
        team["lead"] = (AUDITOR, "lead")
        team.pop("auditor")
        team["extra"] = (LEAD, "auditor")
    if gap == "two_leads":
        team["auditor"] = (AUDITOR, "lead")
    for actor, role in team.values():
        _member(client, engagement_id, actor, role)
        if gap == "declaration" and actor == SUPERVISOR:
            continue
        _declare(client, engagement_id, actor, conflict=gap == "conflict" and actor == AUDITOR)
    return _fail(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(LEAD)), 409)


@pytest.mark.parametrize(
    ("gap", "named"),
    [
        ("criterion", "criterion"),
        ("lead", "lead"),
        ("lead_mismatch", "lead"),
        ("two_leads", "lead"),
        ("supervisor", "supervisor"),
        ("declaration", SUPERVISOR),
        ("conflict", AUDITOR),
    ],
)
def test_engagement_start_names_the_missing_prerequisite(gap: str, named: str) -> None:
    """Verify each missing start prerequisite is named in the rejection next action."""
    body = _start_missing(_client(), gap)
    assert named in body["next_action"]


def test_conflict_redeclaration_is_appended_and_latest_wins() -> None:
    """Preserve numbered declarations while the latest conflict clearance permits fieldwork."""
    client = _client()
    program_id = _program(client)
    engagement_id = _engagement(client, program_id)
    _criterion(client, engagement_id)
    for actor, role in ((LEAD, "lead"), (SUPERVISOR, "supervisor")):
        _member(client, engagement_id, actor, role)
        _declare(client, engagement_id, actor)
    _declare(client, engagement_id, LEAD, conflict=True)
    _fail(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(LEAD)), 409)
    _declare(client, engagement_id, LEAD, conflict=False)
    _ok(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(LEAD)), 200)
    view = _ok(client.get(f"/audit-engagements/{engagement_id}", headers=h(LEAD)), 200)
    numbers = sorted(
        item["declaration_number"]
        for item in view["independence_declarations"]
        if item["auditor_actor"] == LEAD
    )
    assert numbers == [1, 2, 3]


def test_planning_changes_are_limited_to_planned_engagements_and_planners() -> None:
    """Validate planning inputs, planner roles, and restrictions after fieldwork starts."""
    client = _client()
    ids = _ready(client)
    engagement_id = ids["engagement"]
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(LEAD),
            json={"framework": "isms_p_2023", "catalog_identifier": "2.5.1"},
        ),
        409,
    )
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(LEAD),
            json={"framework": "isms_p_2023", "catalog_identifier": "9.9.9"},
        ),
        404,
    )
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(LEAD),
            json={"framework": "made_up", "catalog_identifier": "2.5.1"},
        ),
        422,
    )
    referenced = _ok(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(AUTHORITY),
            json={
                "framework": "iso27001_2022",
                "catalog_identifier": "A.5.15",
                "internal_control_reference": "ic-iam-07 (pending Issue #27)",
            },
        )
    )
    assert referenced["internal_control_reference"] == "ic-iam-07 (pending Issue #27)"
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(AUDITOR),
            json={"framework": "soc2_tsc_2017", "catalog_identifier": "CC6.1"},
        ),
        403,
    )
    member = {"auditor_actor": AUDITOR, "team_role": "auditor", "competence_statement": "CISA."}
    _fail(client.post(f"/audit-engagements/{engagement_id}/team-members", headers=h(AUTHORITY), json=member), 409)
    blank = dict(member, auditor_actor="new-auditor", competence_statement="   ")
    _fail(client.post(f"/audit-engagements/{engagement_id}/team-members", headers=h(AUTHORITY), json=blank), 422)
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/independence-declarations",
            headers=h(OWNER),
            json={"has_conflict": False, "declaration_statement": "Not on the team."},
        ),
        403,
    )
    _fail(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(AUDITOR)), 403)
    _ok(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(LEAD)), 200)
    _fail(client.post(f"/audit-engagements/{engagement_id}/start", headers=h(LEAD)), 409)
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/team-members",
            headers=h(AUTHORITY),
            json=dict(member, auditor_actor=OWNER),
        ),
        409,
    )
    _fail(
        client.post(
            f"/audit-engagements/{engagement_id}/criteria",
            headers=h(LEAD),
            json={"framework": "soc2_tsc_2017", "catalog_identifier": "CC6.1"},
        ),
        409,
    )


def test_sampling_is_reproducible_and_validated() -> None:
    """Verify reproducible sorted samples and reject inconsistent selection parameters."""
    assert select_sample_ordinals("seeded_random", 240, 25, SEED, None) == EXPECTED_SAMPLE
    assert select_sample_ordinals("seeded_random", 240, 25, SEED, None) == EXPECTED_SAMPLE
    assert select_sample_ordinals("full_population", 4, 4, None, None) == [1, 2, 3, 4]
    assert select_sample_ordinals("judgmental", 50, 3, None, [40, 7, 19]) == [7, 19, 40]
    invalid = [
        ("seeded_random", 240, 25, None, None),
        ("seeded_random", 240, 25, SEED, [1]),
        ("full_population", 4, 3, None, None),
        ("full_population", 4, 4, SEED, None),
        ("judgmental", 50, 3, None, None),
        ("judgmental", 50, 3, SEED, [1, 2, 3]),
        ("judgmental", 50, 3, None, [1, 2, 2]),
        ("judgmental", 50, 3, None, [1, 2, 51]),
        ("judgmental", 50, 3, None, [0, 1, 2]),
        ("judgmental", 50, 3, None, [1, 2]),
        ("seeded_random", 10, 11, SEED, None),
    ]
    for method, population, sample, seed, ordinals in invalid:
        with pytest.raises(AuditWorkflowError) as error:
            select_sample_ordinals(method, population, sample, seed, ordinals)
        assert error.value.status_code == 400
        assert error.value.next_action


def test_procedures_require_fieldwork_team_and_own_criterion() -> None:
    """Reject invalid procedure context and inputs while accepting judgmental sampling."""
    client = _client()
    ids = _ready(client)
    _fail(_procedure(client, ids), 409)
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/start", headers=h(LEAD)), 200)
    _fail(_procedure(client, ids, sample_size=241), 400)
    _fail(_procedure(client, ids, population_size=0), 422)
    _fail(_procedure(client, ids, unexpected_field="x"), 422)
    _fail(_procedure(client, ids, engagement_criterion_id="missing"), 404)
    other = _fieldwork(client)
    _fail(_procedure(client, ids, engagement_criterion_id=other["criterion"]), 404)
    outsider = client.post(
        f"/audit-engagements/{ids['engagement']}/procedures",
        headers=h(OWNER),
        json={
            "engagement_criterion_id": ids["criterion"],
            "procedure_description": "x",
            "population_description": "y",
            "population_size": 4,
            "selection_method": "full_population",
            "sample_size": 4,
        },
    )
    _fail(outsider, 403)
    judged = _ok(
        _procedure(
            client,
            ids,
            selection_method="judgmental",
            selection_seed=None,
            population_size=50,
            sample_size=3,
            selected_ordinals=[40, 7, 19],
        )
    )
    assert judged["selected_ordinals"] == [7, 19, 40]


def test_evidence_links_require_known_targets_and_fieldwork() -> None:
    """Validate evidence targets and team membership, then stop linking after reporting."""
    client = _client()
    ids = _fieldwork(client)
    procedure_id = _ok(_procedure(client, ids))["audit_procedure_id"]
    evidence_id = _evidence(client)
    link_url = f"/audit-procedures/{procedure_id}/evidence-links"
    _fail(client.post(link_url, headers=h(AUDITOR), json={"evidence_record_id": "missing"}), 404)
    _fail(
        client.post(link_url, headers=h(AUDITOR), json={"evidence_record_id": evidence_id, "population_ordinal": 4}),
        404,
    )
    _fail(client.post(link_url, headers=h(OWNER), json={"evidence_record_id": evidence_id}), 403)
    _fail(
        client.post("/audit-procedures/missing/evidence-links", headers=h(AUDITOR), json={"evidence_record_id": evidence_id}),
        404,
    )
    _fail(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 409)
    _ok(client.post(link_url, headers=h(AUDITOR), json={"evidence_record_id": evidence_id}))
    _fail(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(AUDITOR)), 403)
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 200)
    _fail(client.post(link_url, headers=h(AUDITOR), json={"evidence_record_id": evidence_id}), 409)
    _fail(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 409)


def test_reporting_requires_at_least_one_procedure() -> None:
    """Reject reporting without a procedure and name the prerequisite in the next action."""
    client = _client()
    ids = _fieldwork(client)
    body = _fail(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 409)
    assert "procedure" in body["next_action"]


def test_findings_require_fieldwork_and_an_independent_owner() -> None:
    """Reject finding creation with invalid state, ownership, criteria, inputs, or headers."""
    client = _client()
    ids = _ready(client)
    url = f"/audit-engagements/{ids['engagement']}/findings"
    _fail(client.post(url, headers=h(AUDITOR), json=_finding_payload(ids)), 409)
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/start", headers=h(LEAD)), 200)
    _fail(client.post(url, headers=h(AUDITOR), json=_finding_payload(ids, remediation_owner_actor=SUPERVISOR)), 409)
    _fail(client.post(url, headers=h(AUDITOR), json=_finding_payload(ids, engagement_criterion_id="missing")), 404)
    _fail(client.post(url, headers=h(OWNER), json=_finding_payload(ids)), 403)
    _fail(client.post(url, headers=h(AUDITOR), json=_finding_payload(ids, severity_rating="severe")), 422)
    _fail(client.post(url, headers=h(AUDITOR), json=_finding_payload(ids, rating_rationale=" ")), 422)
    _fail(client.post(url, headers=h(AUDITOR, "remediation_tracking"), json=_finding_payload(ids)), 403)
    _fail(client.post(url, headers={"X-Purpose": "audit_engagement"}, json=_finding_payload(ids)), 401)
    _fail(client.post(url, headers=h(AUDITOR, "not_a_purpose"), json=_finding_payload(ids)), 403)


def test_revisions_reject_outsiders_and_foreign_criteria() -> None:
    """Reject finding revisions by outsiders, with foreign criteria, or with a zero token."""
    client = _client()
    ids = _fieldwork(client)
    finding_id = _finding(client, ids)
    other = _fieldwork(client)
    base = {
        key: value
        for key, value in _finding_payload(ids).items()
        if key not in {"remediation_owner_actor", "target_date"}
    }
    url = f"/audit-findings/{finding_id}/revisions"
    _fail(client.post(url, headers=h(OWNER), json=dict(base, expected_revision=1)), 403)
    _fail(
        client.post(url, headers=h(AUDITOR), json=dict(base, expected_revision=1, engagement_criterion_id=other["criterion"])),
        404,
    )
    _fail(client.post(url, headers=h(AUDITOR), json=dict(base, expected_revision=0)), 422)


def test_stale_revision_from_a_second_session_is_a_conflict(tmp_path: Path) -> None:
    """Return a conflict when a second session submits an already-consumed revision token."""
    from cwl_grc.audit_management import revise_finding
    from cwl_grc.audit_requests import FindingRevisionRequest
    from cwl_grc.authorization import AuthorizationDecision

    database_url = f"sqlite:///{tmp_path / 'audit.sqlite'}"
    client = TestClient(create_app(database_url=database_url, evidence_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    ids = _fieldwork(client)
    finding_id = _finding(client, ids)
    request = FindingRevisionRequest(
        expected_revision=1,
        **{
            key: value
            for key, value in _finding_payload(ids).items()
            if key not in {"remediation_owner_actor", "target_date"}
        },
    )
    factory = client.app.state.session_factory
    first = factory()
    second = factory()
    try:
        decision = AuthorizationDecision(LEAD, PurposeCode.AUDIT_ENGAGEMENT)
        revise_finding(first, decision, finding_id, request)
        first.commit()
        with pytest.raises(AuditWorkflowError) as conflict:
            revise_finding(second, AuthorizationDecision(AUDITOR, PurposeCode.AUDIT_ENGAGEMENT), finding_id, request)
        assert conflict.value.status_code == 409
    finally:
        first.close()
        second.close()


def test_remediation_actions_belong_to_the_owner() -> None:
    """Enforce remediation purpose, independent assignment, and evidence-backed completion."""
    client = _client()
    ids = _fieldwork(client)
    finding_id = _finding(client, ids)
    url = f"/audit-findings/{finding_id}/remediation-actions"
    action = {"action_description": "Fix feed.", "owner_actor": ENGINEER, "due_date": "2026-10-31"}
    _fail(client.post(url, headers=h(OWNER), json=action), 403)
    _fail(client.post(url, headers=h(LEAD, "remediation_tracking"), json=action), 403)
    _fail(client.post(url, headers=h(OWNER, "remediation_tracking"), json=dict(action, owner_actor=AUDITOR)), 409)
    action_id = _action(client, finding_id)
    finding = _ok(client.get(f"/audit-findings/{finding_id}", headers=h(LEAD)), 200)
    assert finding["finding_status"] == "remediation"
    evidence_id = _evidence(client)
    _fail(_complete(client, action_id, evidence_id, actor=OWNER), 403)
    _fail(_complete(client, action_id, "missing"), 404)
    _fail(_complete(client, "missing", evidence_id), 404)
    _fail(
        client.post(
            f"/remediation-actions/{action_id}/completion",
            headers=h(ENGINEER),
            json={"completion_evidence_record_id": evidence_id},
        ),
        403,
    )
    _ok(_complete(client, action_id, evidence_id), 200)
    _fail(_complete(client, action_id, evidence_id), 409)


def test_retest_requires_completed_actions_and_an_independent_auditor() -> None:
    """Verify retest prerequisites, independent actors, and failed-to-passed closure guards."""
    client = _client()
    ids = _fieldwork(client)
    finding_id = _finding(client, ids)
    evidence_id = _evidence(client)
    body = _fail(_retest(client, finding_id, evidence_id, "passed"), 409)
    assert "remediation action" in body["next_action"]
    action_id = _action(client, finding_id)
    body = _fail(_retest(client, finding_id, evidence_id, "passed"), 409)
    assert action_id in body["next_action"]
    _ok(_complete(client, action_id, evidence_id), 200)
    _fail(_retest(client, finding_id, evidence_id, "passed", actor=OWNER), 403)
    _fail(_retest(client, finding_id, evidence_id, "passed", actor=ENGINEER), 403)
    _fail(_retest(client, finding_id, "missing", "passed"), 404)
    _declare(client, ids["engagement"], AUDITOR, conflict=True)
    body = _fail(_retest(client, finding_id, evidence_id, "passed"), 409)
    assert AUDITOR in body["next_action"]

    failed = _ok(_retest(client, finding_id, evidence_id, "failed", actor=SUPERVISOR))
    assert failed["finding_status"] == "retest_failed"
    close_url = f"/audit-findings/{finding_id}/closure"
    passed_close = {"closure_basis": "retest_passed", "closure_rationale": "Retest passed."}
    _fail(client.post(close_url, headers=h(LEAD), json=passed_close), 409)
    second_action = _action(client, finding_id)
    finding = _ok(client.get(f"/audit-findings/{finding_id}", headers=h(LEAD)), 200)
    assert finding["finding_status"] == "remediation"
    _ok(_complete(client, second_action, evidence_id), 200)
    passed = _ok(_retest(client, finding_id, evidence_id, "passed", actor=SUPERVISOR))
    assert passed["retest_number"] == 2
    assert passed["finding_status"] == "remediation"
    _fail(
        client.post(
            f"/audit-findings/{finding_id}/remediation-actions",
            headers=h(OWNER, "remediation_tracking"),
            json={"action_description": "More.", "owner_actor": ENGINEER, "due_date": "2026-12-01"},
        ),
        409,
    )
    _fail(client.post(close_url, headers=h(AUDITOR), json=passed_close), 403)
    _ok(client.post(close_url, headers=h(SUPERVISOR), json=passed_close))
    _fail(client.post(close_url, headers=h(LEAD), json=passed_close), 409)
    _fail(_retest(client, finding_id, evidence_id, "passed", actor=LEAD), 409)
    _fail(
        client.post(
            f"/audit-findings/{finding_id}/revisions",
            headers=h(LEAD),
            json={
                "expected_revision": 1,
                **{
                    key: value
                    for key, value in _finding_payload(ids).items()
                    if key not in {"remediation_owner_actor", "target_date"}
                },
            },
        ),
        409,
    )
    _fail(
        client.post(
            f"/audit-findings/{finding_id}/remediation-actions",
            headers=h(OWNER, "remediation_tracking"),
            json={"action_description": "Late.", "owner_actor": ENGINEER, "due_date": "2026-12-01"},
        ),
        409,
    )


def test_closure_without_any_retest_is_a_conflict() -> None:
    """Reject retest-based closure without a retest and identify the required next action."""
    client = _client()
    ids = _remediated(client)
    body = _fail(
        client.post(
            f"/audit-findings/{ids['finding']}/closure",
            headers=h(LEAD),
            json={"closure_basis": "retest_passed", "closure_rationale": "No retest yet."},
        ),
        409,
    )
    assert "retest" in body["next_action"]


def test_risk_acceptance_is_time_bounded_and_by_a_different_authority() -> None:
    """Require a separate risk authority and a future expiry no more than 365 days away."""
    client = _client()
    ids = _remediated(client)
    _ok(_retest(client, ids["finding"], ids["evidence"], "failed"))
    url = f"/audit-findings/{ids['finding']}/closure"
    today = date.today()

    def accept(authority: str | None, expires: date | None) -> object:
        """Submit a risk acceptance closure."""
        payload: dict[str, object] = {
            "closure_basis": "risk_accepted",
            "closure_rationale": "Compensating weekly manual leaver review until IdP migration.",
        }
        if authority is not None:
            payload["acceptance_authority_actor"] = authority
        if expires is not None:
            payload["acceptance_expires_on"] = expires.isoformat()
        return client.post(url, headers=h(LEAD), json=payload)

    _fail(accept(None, today + timedelta(days=90)), 400)
    _fail(accept(RISK_AUTHORITY, None), 400)
    _fail(accept(OWNER, today + timedelta(days=90)), 409)
    _fail(accept(AUDITOR, today + timedelta(days=90)), 409)
    _fail(accept(RISK_AUTHORITY, today), 400)
    _fail(accept(RISK_AUTHORITY, today + timedelta(days=366)), 400)
    accepted = _ok(accept(RISK_AUTHORITY, today + timedelta(days=365)))
    assert accepted["finding_status"] == "risk_accepted"
    assert accepted["acceptance_authority_actor"] == RISK_AUTHORITY
    assert accepted["finding_retest_id"] is None
    _fail(_retest(client, ids["finding"], ids["evidence"], "passed"), 409)
    history = _ok(client.get(f"/audit-findings/{ids['finding']}", headers=h(LEAD)), 200)
    assert history["closure"]["acceptance_expires_on"] == (today + timedelta(days=365)).isoformat()


def test_engagement_closure_waits_for_every_finding() -> None:
    """Reject premature or unauthorized closure and leave unresolved findings blocking it."""
    client = _client()
    ids = _fieldwork(client)
    procedure_id = _ok(_procedure(client, ids, selection_method="full_population", selection_seed=None, population_size=3, sample_size=3))[
        "audit_procedure_id"
    ]
    evidence_id = _evidence(client)
    _ok(
        client.post(
            f"/audit-procedures/{procedure_id}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": evidence_id, "population_ordinal": 2},
        )
    )
    _finding(client, ids)
    _fail(client.post(f"/audit-engagements/{ids['engagement']}/closure", headers=h(LEAD)), 409)
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 200)
    _declare(client, ids["engagement"], AUDITOR, conflict=True)
    body = _fail(client.post(f"/audit-engagements/{ids['engagement']}/closure", headers=h(LEAD)), 409)
    assert "finding" in body["next_action"]
    _fail(client.post(f"/audit-engagements/{ids['engagement']}/closure", headers=h(AUDITOR)), 403)
    _fail(
        client.post(
            f"/audit-engagements/{ids['engagement']}/findings",
            headers=h(AUDITOR),
            json=_finding_payload(ids),
        ),
        409,
    )


def test_declarations_close_with_the_engagement() -> None:
    """Reject new independence declarations after the engagement has closed."""
    client = _client()
    ids = _fieldwork(client)
    procedure = _ok(_procedure(client, ids))
    _ok(
        client.post(
            f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": _evidence(client)},
        )
    )
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 200)
    _ok(client.post(f"/audit-engagements/{ids['engagement']}/closure", headers=h(LEAD)), 200)
    _fail(
        client.post(
            f"/audit-engagements/{ids['engagement']}/independence-declarations",
            headers=h(AUDITOR),
            json={"has_conflict": False, "declaration_statement": "Late."},
        ),
        409,
    )


def test_overdue_remediation_is_visible() -> None:
    """List only overdue unresolved work, default to today, and validate query headers and dates."""
    client = _client()
    ids = _fieldwork(client)
    late_finding = _finding(client, ids, target_date="2026-10-15")
    late_action = _action(client, late_finding, due="2026-10-10")
    on_time_action = _action(client, late_finding, due="2026-10-20")
    done_action = _action(client, late_finding, due="2026-10-01")
    _ok(_complete(client, done_action, _evidence(client)), 200)
    _finding(client, ids, target_date="2026-12-31")
    response = _ok(
        client.get("/audit-remediation/overdue", params={"as_of": "2026-10-20"}, headers=h(SUPERVISOR)),
        200,
    )
    assert response["as_of"] == "2026-10-20"
    assert [item["remediation_action_id"] for item in response["overdue_actions"]] == [late_action]
    assert response["overdue_actions"][0]["finding_status"] == "remediation"
    assert [item["audit_finding_id"] for item in response["overdue_findings"]] == [late_finding]
    assert on_time_action not in str(response)
    default = _ok(client.get("/audit-remediation/overdue", headers=h(SUPERVISOR)), 200)
    assert default["as_of"] == date.today().isoformat()
    _fail(client.get("/audit-remediation/overdue", params={"as_of": "20-10-2026"}, headers=h(SUPERVISOR)), 422)
    _fail(client.get("/audit-remediation/overdue"), 401)


def test_overdue_service_excludes_resolved_findings() -> None:
    """Exclude closed findings and completed actions from the overdue service results."""
    client = _client()
    ids = _remediated(client)
    _ok(_retest(client, ids["finding"], ids["evidence"], "passed"))
    _ok(
        client.post(
            f"/audit-findings/{ids['finding']}/closure",
            headers=h(LEAD),
            json={"closure_basis": "retest_passed", "closure_rationale": "Retest passed."},
        )
    )
    with client.app.state.session_factory() as session:
        result = list_overdue_remediation(session, today=date(2027, 6, 1))
        assert result.overdue_findings == []
        assert result.overdue_actions == []
        result = list_overdue_remediation(session)
        assert result.as_of == date.today()


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/audit-programs/missing/approval", None),
        ("post", "/audit-programs/missing/engagements", {
            "engagement_title": "x", "scope_statement": "y", "period_start": "2026-07-01",
            "period_end": "2026-09-30", "lead_auditor_actor": LEAD,
        }),
        ("get", "/audit-engagements/missing", None),
        ("post", "/audit-engagements/missing/criteria", {"framework": "isms_p_2023", "catalog_identifier": "2.5.1"}),
        ("post", "/audit-engagements/missing/team-members", {
            "auditor_actor": AUDITOR, "team_role": "auditor", "competence_statement": "CISA.",
        }),
        ("post", "/audit-engagements/missing/independence-declarations", {
            "has_conflict": False, "declaration_statement": "None.",
        }),
        ("post", "/audit-engagements/missing/start", None),
        ("post", "/audit-engagements/missing/reporting", None),
        ("post", "/audit-engagements/missing/closure", None),
        ("post", "/audit-engagements/missing/procedures", {
            "engagement_criterion_id": "x", "procedure_description": "x", "population_description": "y",
            "population_size": 4, "selection_method": "full_population", "sample_size": 4,
        }),
        ("post", "/audit-engagements/missing/findings", {
            "engagement_criterion_id": "x", "condition_statement": "c", "cause_statement": "c",
            "effect_statement": "e", "severity_rating": "low", "rating_rationale": "r",
            "recommendation_text": "r", "remediation_owner_actor": OWNER, "target_date": "2026-12-01",
        }),
        ("post", "/audit-findings/missing/revisions", {
            "expected_revision": 1, "engagement_criterion_id": "x", "condition_statement": "c",
            "cause_statement": "c", "effect_statement": "e", "severity_rating": "low",
            "rating_rationale": "r", "recommendation_text": "r",
        }),
        ("get", "/audit-findings/missing", None),
        ("post", "/audit-findings/missing/retests", {
            "procedure_description": "x", "retest_result": "passed",
            "effectiveness_conclusion": "y", "evidence_record_id": "z",
        }),
        ("post", "/audit-findings/missing/closure", {
            "closure_basis": "retest_passed", "closure_rationale": "x",
        }),
    ],
)
def test_unknown_audit_identifiers_return_not_found(method: str, path: str, json_body: dict | None) -> None:
    """Return a not-on-file rejection for each parameterized missing audit target."""
    client = _client()
    kwargs: dict[str, object] = {"headers": h(AUTHORITY)}
    if json_body is not None:
        kwargs["json"] = json_body
    body = _fail(getattr(client, method)(path, **kwargs), 404)
    assert "not on file" in body["detail"]


def test_unknown_finding_for_remediation_tracking_returns_not_found() -> None:
    """Reject remediation action creation for a finding that is not on file."""
    client = _client()
    response = client.post(
        "/audit-findings/missing/remediation-actions",
        headers=h(OWNER, "remediation_tracking"),
        json={"action_description": "x", "owner_actor": ENGINEER, "due_date": "2026-12-01"},
    )
    _fail(response, 404)


def test_strict_request_validation_states_the_next_action() -> None:
    """Reject an undeclared program field with validation detail and a next action."""
    client = _client()
    response = client.post(
        "/audit-programs",
        headers=h(PLANNER),
        json={
            "program_title": "Program",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "risk_rationale": "Annual.",
            "audit_authority_actor": AUTHORITY,
            "tenant_id": "smuggled",
        },
    )
    body = _fail(response, 422)
    assert body["detail"]


def test_audit_purposes_are_labelled() -> None:
    """Verify the exact officer-facing labels for audit and remediation purposes."""
    assert purpose_label(PurposeCode.AUDIT_ENGAGEMENT) == "Plan, perform, and close an audit engagement"
    assert purpose_label(PurposeCode.REMEDIATION_TRACKING) == "Record remediation of an audit finding"


def test_immutable_audit_records_reject_update_and_delete() -> None:
    """Verify SQL guards reject updates and deletes of immutable audit records."""
    client = _client()
    ids = _remediated(client)
    _ok(_retest(client, ids["finding"], ids["evidence"], "passed"))
    _ok(
        client.post(
            f"/audit-findings/{ids['finding']}/closure",
            headers=h(LEAD),
            json={"closure_basis": "retest_passed", "closure_rationale": "Retest passed."},
        )
    )
    tables = {
        "audit_finding_revision": "rating_rationale",
        "independence_declaration": "declaration_statement",
        "finding_retest": "effectiveness_conclusion",
        "finding_closure": "closure_rationale",
    }
    with client.app.state.session_factory() as session:
        for table, column in tables.items():
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(text(f"UPDATE {table} SET {column} = 'tampered'"))
            session.rollback()
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(text(f"DELETE FROM {table}"))
            session.rollback()


def test_evidence_link_needs_exactly_one_target() -> None:
    """Verify the database rejects an evidence link with neither procedure nor sample target."""
    client = _client()
    evidence_id = _evidence(client)
    with client.app.state.session_factory() as session:
        session.add(
            AuditEvidenceLink(
                audit_evidence_link_id=uuid4().hex,
                evidence_record_id=evidence_id,
                audit_procedure_id=None,
                audit_sample_item_id=None,
                linked_by_actor=AUDITOR,
                linked_at=datetime(2026, 10, 6, 9, 0),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_status_columns_reject_unknown_values() -> None:
    """Reject an unsupported program status and verify the audit model table names."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        session.add(
            AuditProgram(
                audit_program_id="p",
                program_title="t",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 12, 31),
                risk_rationale="r",
                audit_authority_actor=AUTHORITY,
                created_by_actor=PLANNER,
                created_at=datetime(2026, 1, 1),
                program_status="archived",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    assert AuditEngagement.__tablename__ == "audit_engagement"
    assert AuditFinding.__tablename__ == "audit_finding"
    assert RemediationAction.__tablename__ == "remediation_action"


def test_audit_management_receipt_is_idempotent(tmp_path: Path) -> None:
    """Apply migrations twice and verify one receipt for each expected migration key."""
    engine = create_engine(f"sqlite:///{tmp_path / 'receipts.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE policy_document (policy_document_id VARCHAR(64) PRIMARY KEY, "
                "policy_title VARCHAR(255) NOT NULL, created_by_actor VARCHAR(128) NOT NULL, "
                "created_at TIMESTAMP NOT NULL, current_version_number INTEGER NOT NULL DEFAULT 0)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE policy_version (policy_version_id VARCHAR(64) PRIMARY KEY, "
                "policy_document_id VARCHAR(64) NOT NULL, version_number INTEGER NOT NULL, "
                "policy_body TEXT NOT NULL, authored_by_actor VARCHAR(128) NOT NULL, "
                "authored_at TIMESTAMP NOT NULL, is_finalized BOOLEAN NOT NULL DEFAULT TRUE)"
            )
        )
    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    with engine.connect() as connection:
        keys = sorted(
            row[0] for row in connection.execute(text("SELECT migration_key FROM schema_migration"))
        )
    assert keys == sorted([POLICY_INTEGRITY_MIGRATION, AUDIT_MANAGEMENT_MIGRATION])
    assert AUDIT_MANAGEMENT_MIGRATION == "0002_audit_management"


def test_audit_integrity_guard_ddl_covers_sqlite_and_postgresql() -> None:
    """Verify SQLite and PostgreSQL guard DDL covers immutable audit records and events."""
    sqlite_ddl = "\n".join(integrity_guard_statements("sqlite"))
    postgres_ddl = "\n".join(integrity_guard_statements("postgresql"))
    for table in (
        "audit_finding_revision",
        "independence_declaration",
        "finding_retest",
        "finding_closure",
    ):
        assert f"{table}_block_update" in sqlite_ddl
        assert f"{table}_block_delete" in sqlite_ddl
        assert f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}" in postgres_ddl
        assert f"BEFORE UPDATE OR DELETE ON {table}" in postgres_ddl
    assert "CREATE OR REPLACE FUNCTION prevent_audit_record_mutation()" in postgres_ddl
    assert "EXECUTE FUNCTION prevent_audit_record_mutation()" in postgres_ddl
    assert "prevent_audit_event_mutation" in postgres_ddl
