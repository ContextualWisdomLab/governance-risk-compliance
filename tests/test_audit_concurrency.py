"""Real SQLite transaction regressions for finding decision serialization."""

from threading import Event, Thread

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import event

from cwl_grc import create_app
from cwl_grc import audit_management as service
from cwl_grc.audit_requests import (
    FindingRevisionRequest,
    FindingRetestRequest,
    FindingClosureRequest,
    RemediationActionRequest,
)
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.models import (
    AuditFinding,
    AuditFindingRevision,
    AuditEvent,
    FindingRetest,
    FindingClosure,
    RemediationAction,
)
from test_audit_management import AUDITOR, LEAD, OWNER, ENGINEER, _remediated, _finding_payload


def _setup(tmp_path):
    """Seed the official ISMS-P 2.5.1 workflow in a file-backed database."""
    client = TestClient(
        create_app(
            database_url=f"sqlite:///{tmp_path / 'concurrency.sqlite'}",
            evidence_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        )
    )
    ids = _remediated(client)
    payload = _finding_payload(ids)
    payload.pop("remediation_owner_actor")
    payload.pop("target_date")
    revision = FindingRevisionRequest(expected_revision=1, **payload)
    retest = FindingRetestRequest(
        procedure_description="Reperform leaver sample after webhook go-live.",
        retest_result="passed",
        effectiveness_conclusion="Leavers deprovisioned within one business day.",
        evidence_record_id=ids["evidence"],
    )
    return client.app.state.session_factory, ids, revision, retest


def _decision(actor=AUDITOR):
    """Declare the established officer and audit purpose."""
    return AuthorizationDecision(actor, PurposeCode.AUDIT_ENGAGEMENT)


@pytest.mark.parametrize("operation", ["revision", "action", "closure", "retest"])
def test_finding_decisions_have_a_single_database_order(tmp_path, monkeypatch, operation):
    """Pause a decision guard and observe actual independent transaction ordering."""
    factory, ids, revision, retest = _setup(tmp_path)
    if operation == "closure":
        with factory() as session:
            service.record_retest(session, _decision(), ids["finding"], retest)
            session.commit()
        retest = retest.model_copy(update={"retest_result": "failed"})
    guarded, release, attempted, finished = (Event() for _ in range(4))
    outcomes = {}
    original = service._latest_retest
    first_session = []

    def pause(session, finding_id):
        value = original(session, finding_id)
        if session is first_session[0]:
            guarded.set()
            assert release.wait(5), "guard release timed out"
        return value

    def execute(session, name, operation):
        try:
            operation(session)
            session.commit()
            outcomes[name] = "committed"
        except service.AuditWorkflowError as error:
            session.rollback()
            outcomes[name] = error.status_code
        except BaseException as error:
            session.rollback()
            outcomes[name] = error
        finally:
            session.close()
            if name == "retest":
                finished.set()

    def observe(connection, cursor, statement, parameters, context, executemany):
        if "UPDATE audit_finding" in statement or "INSERT INTO finding_retest" in statement:
            attempted.set()

    first = factory()
    first_session.append(first)
    monkeypatch.setattr(service, "_latest_retest", pause)
    operations = {
        "retest": lambda s: service.record_retest(
            s, _decision(), ids["finding"], retest.model_copy(update={"retest_result": "failed"})
        ),
        "revision": lambda s: service.revise_finding(s, _decision(LEAD), ids["finding"], revision),
        "action": lambda s: service.create_remediation_action(
            s,
            _decision(OWNER),
            ids["finding"],
            RemediationActionRequest(
                action_description="Add webhook monitoring.",
                owner_actor=ENGINEER,
                due_date="2026-11-30",
            ),
        ),
        "closure": lambda s: service.close_finding(
            s,
            _decision(LEAD),
            ids["finding"],
            FindingClosureRequest(closure_basis="retest_passed", closure_rationale="Verified."),
        ),
    }
    t1 = Thread(target=execute, args=(first, "first", operations[operation]), daemon=True)
    t2 = Thread(
        target=lambda: execute(
            factory(),
            "retest",
            lambda s: service.record_retest(s, _decision(), ids["finding"], retest),
        ),
        daemon=True,
    )
    t1.start()
    try:
        assert guarded.wait(5), "revision guard not reached"
        event.listen(factory.kw["bind"], "before_cursor_execute", observe)
        t2.start()
        assert attempted.wait(5), "retest write not attempted"
        overtook = finished.wait(0.3)
    finally:
        release.set()
        t1.join(6)
        if t2.ident is not None:
            t2.join(6)
        event.remove(factory.kw["bind"], "before_cursor_execute", observe)
    assert not t1.is_alive() and not t2.is_alive(), "transaction workers timed out"
    assert outcomes == {
        "first": "committed",
        "retest": "committed" if operation in {"revision", "retest"} else 409,
    }, outcomes
    assert not overtook, "retest overtook the first decision between guard read and write"
    with factory() as session:
        finding = session.get(AuditFinding, ids["finding"])
        assert finding.finding_status == ("closed" if operation == "closure" else "remediation")
        assert session.query(RemediationAction).count() == (2 if operation == "action" else 1)
        assert session.query(FindingClosure).count() == (1 if operation == "closure" else 0)
        if operation == "closure":
            closure = session.query(FindingClosure).one()
            assert closure.finding_retest_id == session.query(FindingRetest).one().finding_retest_id
        expected_revision = 2 if operation == "revision" else 1
        assert (
            session.get(AuditFinding, ids["finding"]).current_revision_number == expected_revision
        )
        assert session.query(AuditFindingRevision).count() == expected_revision
        numbers = [
            row.retest_number
            for row in session.query(FindingRetest).order_by(FindingRetest.retest_number)
        ]
        assert numbers == list(range(1, len(numbers) + 1))
        assert session.query(FindingRetest).count() == (
            0 if operation == "action" else 2 if operation == "retest" else 1
        )
        assert session.query(AuditEvent).filter_by(action_name="record_finding_retest").count() == (
            0 if operation == "action" else 2 if operation == "retest" else 1
        )


@pytest.mark.parametrize("operation", ["revision", "action", "closure"])
def test_passing_retest_first_blocks_later_writes_with_cached_finding(
    tmp_path, monkeypatch, operation
):
    """Hold a retest transaction; cached second-session decisions wait then reject."""
    factory, ids, revision, retest = _setup(tmp_path)
    if operation == "closure":
        with factory() as session:
            service.record_retest(session, _decision(), ids["finding"], retest)
            session.commit()
        retest = retest.model_copy(update={"retest_result": "failed"})
    guarded, release, attempted, finished = (Event() for _ in range(4))
    outcomes = {}
    original = service._latest_retest
    first = factory()
    second = factory()
    cached = second.get(AuditFinding, ids["finding"])
    assert cached.current_revision_number == 1
    before_events = second.query(AuditEvent).count()

    def pause(session, finding_id):
        value = original(session, finding_id)
        if session is first:
            guarded.set()
            assert release.wait(5)
        return value

    def worker(session, name, operation):
        try:
            operation(session)
            session.commit()
            outcomes[name] = "committed"
        except service.AuditWorkflowError as error:
            session.rollback()
            outcomes[name] = error.status_code
        except BaseException as error:
            session.rollback()
            outcomes[name] = error
        finally:
            session.close()
            if name == "second":
                finished.set()

    def observe(connection, cursor, statement, parameters, context, executemany):
        if "UPDATE audit_finding" in statement:
            attempted.set()

    def write(session):
        if operation == "closure":
            return service.close_finding(
                session,
                _decision(LEAD),
                ids["finding"],
                FindingClosureRequest(closure_basis="retest_passed", closure_rationale="Verified."),
            )
        if operation == "revision":
            return service.revise_finding(session, _decision(LEAD), ids["finding"], revision)
        return service.create_remediation_action(
            session,
            _decision(OWNER),
            ids["finding"],
            RemediationActionRequest(
                action_description="Add webhook monitoring.",
                owner_actor=ENGINEER,
                due_date="2026-11-30",
            ),
        )

    monkeypatch.setattr(service, "_latest_retest", pause)
    t1 = Thread(
        target=worker,
        args=(
            first,
            "first",
            lambda s: service.record_retest(s, _decision(), ids["finding"], retest),
        ),
        daemon=True,
    )
    t2 = Thread(target=worker, args=(second, "second", write), daemon=True)
    t1.start()
    try:
        assert guarded.wait(5)
        event.listen(factory.kw["bind"], "before_cursor_execute", observe)
        t2.start()
        assert attempted.wait(5)
        assert not finished.wait(0.3), "second transaction did not wait for the passing retest"
    finally:
        release.set()
        t1.join(6)
        if t2.ident is not None:
            t2.join(6)
        event.remove(factory.kw["bind"], "before_cursor_execute", observe)
    assert not t1.is_alive() and not t2.is_alive()
    assert outcomes == {"first": "committed", "second": 409}, outcomes
    with factory() as session:
        assert session.query(AuditEvent).count() == before_events + 1
        assert session.query(AuditFindingRevision).count() == 1
        assert session.query(FindingRetest).count() == (2 if operation == "closure" else 1)
        assert session.query(FindingClosure).count() == 0


@pytest.mark.parametrize("operation", ["revision", "action", "retest", "closure"])
def test_closed_finding_refreshes_cached_state_without_audit_writes(tmp_path, operation):
    """After independent closure, stale identity maps cannot mutate or reopen a finding."""
    factory, ids, revision, retest = _setup(tmp_path)
    with factory() as stale:
        cached = stale.get(AuditFinding, ids["finding"])
        with factory() as fresh:
            service.record_retest(fresh, _decision(), ids["finding"], retest)
            fresh.commit()
            service.close_finding(
                fresh,
                _decision(LEAD),
                ids["finding"],
                FindingClosureRequest(closure_basis="retest_passed", closure_rationale="Verified."),
            )
            fresh.commit()
            before_events = fresh.query(AuditEvent).count()
        assert cached.finding_status == "remediation"
        with pytest.raises(service.AuditWorkflowError) as caught:
            if operation == "revision":
                service.revise_finding(stale, _decision(LEAD), ids["finding"], revision)
            elif operation == "action":
                service.create_remediation_action(
                    stale,
                    _decision(OWNER),
                    ids["finding"],
                    RemediationActionRequest(
                        action_description="Monitor webhook.",
                        owner_actor=ENGINEER,
                        due_date="2026-11-30",
                    ),
                )
            elif operation == "retest":
                service.record_retest(stale, _decision(), ids["finding"], retest)
            else:
                service.close_finding(
                    stale,
                    _decision(LEAD),
                    ids["finding"],
                    FindingClosureRequest(
                        closure_basis="retest_passed", closure_rationale="Verified."
                    ),
                )
        assert caught.value.status_code == 409
        stale.rollback()
        assert stale.query(AuditEvent).count() == before_events
        assert stale.get(AuditFinding, ids["finding"]).finding_status == "closed"
        assert stale.query(AuditFindingRevision).count() == 1
        assert stale.query(FindingRetest).count() == 1


def test_rejected_revision_rolls_back_and_releases_the_database_lock(tmp_path):
    """A stale token writes no history; rollback lets an independent officer proceed."""
    factory, ids, revision, retest = _setup(tmp_path)
    with factory() as first:
        before_events = first.query(AuditEvent).count()
        with pytest.raises(service.AuditWorkflowError) as caught:
            service.revise_finding(
                first,
                _decision(LEAD),
                ids["finding"],
                revision.model_copy(update={"expected_revision": 2}),
            )
        assert caught.value.status_code == 409
        first.rollback()
        with factory() as second:
            service.revise_finding(second, _decision(LEAD), ids["finding"], revision)
            second.commit()
            service.record_retest(second, _decision(), ids["finding"], retest)
            second.commit()
            assert second.query(AuditEvent).count() == before_events + 2
            assert second.query(AuditFindingRevision).count() == 2
            assert second.get(AuditFinding, ids["finding"]).current_revision_number == 2
