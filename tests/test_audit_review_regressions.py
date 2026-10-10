"""Regressions for PR76 review findings, with compatible officer controls."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cwl_grc.audit_management import AuditWorkflowError, select_sample_ordinals
from cwl_grc.audit_requests import AuditProcedureRequest
from test_audit_management import (
    AUDITOR, LEAD, SUPERVISOR, RISK_AUTHORITY, _client, _declare, _events,
    _evidence, _fieldwork, _finding, _finding_payload, _ok, _procedure,
    _remediated, _retest, h,
)


@pytest.mark.parametrize("operation,actor", [
    ("revision", AUDITOR), ("closure", LEAD), ("closure", SUPERVISOR),
    ("risk_acceptance", LEAD), ("reporting", LEAD), ("engagement_closure", LEAD),
])
def test_current_conflict_blocks_decisions_without_writes(operation, actor):
    """Reject decisions without writes during a current conflict, then accept after clearance."""
    client = _client()
    ids = _remediated(client) if operation in {"closure", "risk_acceptance"} else _fieldwork(client)
    if operation in {"closure", "risk_acceptance"}:
        _ok(_retest(client, ids["finding"], ids["evidence"], "passed"))
    if operation == "revision":
        ids["finding"] = _finding(client, ids)
        payload = _finding_payload(ids)
        payload.pop("remediation_owner_actor")
        payload.pop("target_date")
        payload["expected_revision"] = 1
        url = f"/audit-findings/{ids['finding']}/revisions"
        success = 201
    elif operation in {"closure", "risk_acceptance"}:
        payload = {"closure_basis": "retest_passed", "closure_rationale": "Independent verification."}
        if operation == "risk_acceptance":
            from datetime import date, timedelta
            payload.update(closure_basis="risk_accepted", acceptance_authority_actor=RISK_AUTHORITY,
                           acceptance_expires_on=(date.today()+timedelta(days=30)).isoformat())
        url = f"/audit-findings/{ids['finding']}/closure"
        success = 201
    else:
        procedure = _ok(_procedure(client, ids))
        _ok(client.post(f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links",
                        headers=h(AUDITOR), json={"evidence_record_id": _evidence(client)}))
        if operation == "engagement_closure":
            _ok(client.post(f"/audit-engagements/{ids['engagement']}/reporting", headers=h(LEAD)), 200)
        suffix = "closure" if operation == "engagement_closure" else "reporting"
        url = f"/audit-engagements/{ids['engagement']}/{suffix}"
        payload = None
        success = 200
    _declare(client, ids["engagement"], actor, conflict=True)
    before_events = _events(client)
    before_engagement = client.get(f"/audit-engagements/{ids['engagement']}", headers=h(LEAD)).json()
    response = client.post(url, headers=h(actor), json=payload)
    assert response.status_code == 409, response.text
    assert "independen" in response.json()["detail"]
    assert actor in response.json()["next_action"]
    assert _events(client) == before_events
    assert client.get(f"/audit-engagements/{ids['engagement']}", headers=h(LEAD)).json() == before_engagement
    _declare(client, ids["engagement"], actor, conflict=False)
    _ok(client.post(url, headers=h(actor), json=payload), success)


def _sample_request(**overrides):
    """Return a seeded-random access-review request payload with caller overrides."""
    payload = dict(engagement_criterion_id="criterion", procedure_description="Access review",
                   population_description="IdP account register", population_size=240,
                   selection_method="seeded_random", sample_size=25, selection_seed=20260701)
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("overrides", [
    {"population_size": 1_000_001}, {"sample_size": 10_001},
    {"selection_seed": 2**63}, {"selection_seed": -(2**63)-1},
    {"selected_ordinals": [1]*10_001},
])
def test_sampling_request_rejects_unsupported_limits(overrides):
    """Reject sampling request values beyond the supported size and seed limits."""
    with pytest.raises(ValidationError):
        AuditProcedureRequest(**_sample_request(**overrides))


@pytest.mark.parametrize("population,sample,seed,ordinals", [
    (1_000_001, 1, 42, None), (20_000, 10_001, 42, None),
    (240, 25, 2**63, None), (240, 25, -(2**63)-1, None),
    (240, 25, 42, [1]*10_001),
])
def test_public_selector_rejects_limits_before_allocation(population, sample, seed, ordinals):
    """Reject unsupported sampling limits with a workflow error and a next action."""
    with pytest.raises(AuditWorkflowError) as caught:
        select_sample_ordinals("seeded_random", population, sample, seed, ordinals)
    assert caught.value.status_code == 400
    assert "limit" in caught.value.detail.lower()
    assert caught.value.next_action


def test_sampling_limit_edges_preserve_valid_officer_inputs():
    """Accept boundary sizes and seeds with reproducible, sorted, unique sample ordinals."""
    for seed in (-(2**63), -42, 0, 2**63-1):
        model = AuditProcedureRequest(**_sample_request(population_size=1_000_000, sample_size=10_000,
                                                       selection_seed=seed))
        selected = select_sample_ordinals(model.selection_method, model.population_size,
                                         model.sample_size, model.selection_seed, None)
        assert len(selected) == 10_000
        assert selected == sorted(set(selected))
        assert selected == select_sample_ordinals("seeded_random", 1_000_000, 10_000, seed, None)
    assert select_sample_ordinals("full_population", 10_000, 10_000, None, None) == list(range(1, 10_001))
    ordinals = list(range(1, 10_001))
    assert select_sample_ordinals("judgmental", 1_000_000, 10_000, None, ordinals) == ordinals


def test_oversized_http_sampling_is_422_and_preserves_engagement():
    """Reject an oversized HTTP sampling request without recording events or procedures."""
    client = _client()
    ids = _fieldwork(client)
    before = _events(client)
    response = _procedure(client, ids, population_size=1_000_001)
    assert response.status_code == 422
    assert response.json()["next_action"]
    assert _events(client) == before
    assert client.get(f"/audit-engagements/{ids['engagement']}", headers=h(LEAD)).json()["procedures"] == []


@pytest.mark.parametrize("field,value", [
    ("population_size", True), ("population_size", "240"), ("population_size", 240.0),
    ("sample_size", False), ("sample_size", "25"), ("selection_seed", True),
    ("selection_seed", "42"), ("selected_ordinals", [True]),
    ("selected_ordinals", ["1"]), ("selected_ordinals", [1.0]),
])
def test_sampling_json_types_match_declared_integer_schema(field, value):
    """Reject coerced sampling integers, including booleans, strings, and float ordinals."""
    with pytest.raises(ValidationError):
        AuditProcedureRequest(**_sample_request(**{field: value}))


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_independence_requires_a_json_boolean(value):
    """Reject numeric and string conflict flags instead of coercing them to booleans."""
    from cwl_grc.audit_requests import IndependenceDeclarationRequest
    with pytest.raises(ValidationError):
        IndependenceDeclarationRequest(has_conflict=value, declaration_statement="Conflict declaration.")


@pytest.mark.parametrize("value", [1791244800, 1791244800.0, "1791244800", "2026-10-06T00:00:00"])
def test_calendar_date_rejects_undocumented_timestamp_inputs(value):
    """Reject numeric timestamps and datetime strings as audit program calendar dates."""
    from cwl_grc.audit_requests import AuditProgramRequest
    with pytest.raises(ValidationError):
        AuditProgramRequest(program_title="Access audit", period_start=value, period_end="2026-12-31",
                            risk_rationale="Access risk", audit_authority_actor="cae")


def test_strict_calendar_date_and_boolean_preserve_valid_inputs():
    """Accept date objects, ISO calendar strings, and actual boolean conflict flags."""
    from datetime import date
    from cwl_grc.audit_requests import AuditProgramRequest, IndependenceDeclarationRequest
    for day in (date(2026, 1, 1), "2026-01-01"):
        model = AuditProgramRequest(program_title="Access audit", period_start=day, period_end="2026-12-31",
                                    risk_rationale="Access risk", audit_authority_actor="cae")
        assert model.period_start == date(2026, 1, 1)
    for flag in (True, False):
        assert IndependenceDeclarationRequest(has_conflict=flag, declaration_statement="Declared.").has_conflict is flag


@pytest.mark.parametrize("population,sample,seed,ordinals", [
    (True, 1, 42, None), (240.0, 25, 42, None),
    (240, "25", 42, None), (240, 25, True, None),
    (240, 25, 42, [True]), (240, 25, 42, [1.0]),
])
def test_public_selector_rejects_non_integer_sampling_inputs(population, sample, seed, ordinals):
    """Reject non-integer selector inputs with an integer-specific workflow error."""
    with pytest.raises(AuditWorkflowError) as caught:
        select_sample_ordinals("seeded_random", population, sample, seed, ordinals)
    assert caught.value.status_code == 400
    assert "integer" in caught.value.detail.lower()


def _revision_payload(ids, expected=1):
    """Return a critical finding revision payload with the supplied expected revision token."""
    payload = _finding_payload(ids, severity_rating="critical",
                               condition_statement="All sampled accounts retain privileged access.")
    payload.pop("remediation_owner_actor")
    payload.pop("target_date")
    payload["expected_revision"] = expected
    return payload


@pytest.mark.parametrize("result", [None, "failed", "passed"])
def test_revision_retest_state_preserves_verified_finding(result):
    """Block material revision after a passed retest while allowing no-retest or failed states."""
    client = _client()
    ids = _remediated(client)
    if result is not None:
        retest = _ok(_retest(client, ids["finding"], ids["evidence"], result))
    url = f"/audit-findings/{ids['finding']}"
    before = client.get(url, headers=h(LEAD)).json()
    events = _events(client)
    response = client.post(url + "/revisions", headers=h(AUDITOR),
                           json=_revision_payload(ids))
    after = client.get(url, headers=h(LEAD)).json()
    if result == "passed":
        unchanged_events = _events(client) == events
        closure = client.post(url + "/closure", headers=h(SUPERVISOR),
                              json={"closure_basis": "retest_passed",
                                    "closure_rationale": "Close the independently verified finding."})
        print(f"passed retest -> material revision HTTP {response.status_code} -> closure HTTP {closure.status_code}")
        assert response.status_code == 409, response.text
        assert response.json()["next_action"]
        assert "passed" in response.json()["detail"]
        assert after == before
        assert unchanged_events
        closed = _ok(closure)
        assert closed["finding_retest_id"] == retest["finding_retest_id"]
        assert closed["finding_status"] == "closed"
    else:
        _ok(response)
        assert after["current_revision_number"] == 2
        assert after["revisions"][-1]["severity_rating"] == "critical"
        assert len(_events(client)) == len(events) + 1


@pytest.mark.parametrize("field,value", [
    ("population_ordinal", 0), ("population_ordinal", -1),
    ("population_ordinal", 1_000_001), ("population_ordinal", 2**100),
    ("expected_revision", 0), ("expected_revision", 2**31 - 1),
    ("expected_revision", 2**31), ("expected_revision", 2**100),
])
def test_sql_bound_http_integers_reject_unsupported_values_without_writes(field, value):
    """Reject unsupported SQL-bound HTTP integers with JSON 422 and unchanged views and events."""
    from fastapi.testclient import TestClient
    client = TestClient(_client().app, raise_server_exceptions=False)
    ids = _fieldwork(client)
    ids["finding"] = _finding(client, ids)
    procedure = _ok(_procedure(client, ids))
    evidence = _evidence(client)
    engagement_url = f"/audit-engagements/{ids['engagement']}"
    finding_url = f"/audit-findings/{ids['finding']}"
    before_engagement = client.get(engagement_url, headers=h(LEAD)).json()
    before_finding = client.get(finding_url, headers=h(LEAD)).json()
    events = _events(client)
    if field == "population_ordinal":
        url = f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links"
        payload = {"evidence_record_id": evidence, field: value}
    else:
        url = finding_url + "/revisions"
        payload = _revision_payload(ids, expected=value)
    response = client.post(url, headers=h(AUDITOR), json=payload)
    print(f"{field}={value}: HTTP {response.status_code}, content-type={response.headers.get('content-type')}")
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"]
    assert response.json()["next_action"]
    assert _events(client) == events
    assert client.get(engagement_url, headers=h(LEAD)).json() == before_engagement
    assert client.get(finding_url, headers=h(LEAD)).json() == before_finding


def test_sql_bound_integer_upper_edges_reach_normal_workflow():
    """Accept edge sample ordinals and route a valid stale revision token to a workflow conflict."""
    client = _client()
    ids = _fieldwork(client)
    finding = _finding(client, ids)
    procedure = _ok(_procedure(client, ids, population_size=1_000_000, sample_size=2,
                               selection_method="judgmental", selection_seed=None,
                               selected_ordinals=[1, 1_000_000]))
    evidence = _evidence(client)
    for ordinal in (1, 1_000_000):
        link = _ok(client.post(
            f"/audit-procedures/{procedure['audit_procedure_id']}/evidence-links",
            headers=h(AUDITOR),
            json={"evidence_record_id": evidence, "population_ordinal": ordinal}))
        assert link["audit_sample_item_id"]
    url = f"/audit-findings/{finding}"
    before = client.get(url, headers=h(LEAD)).json()
    events = _events(client)
    response = client.post(url + "/revisions", headers=h(AUDITOR),
                           json=_revision_payload(ids, expected=2**31 - 2))
    assert response.status_code == 409, response.text
    assert response.json()["next_action"]
    assert "changed" in response.json()["detail"]
    assert _events(client) == events
    assert client.get(url, headers=h(LEAD)).json() == before
    assert _ok(client.post(url + "/revisions", headers=h(AUDITOR),
                           json=_revision_payload(ids)))["current_revision_number"] == 2
