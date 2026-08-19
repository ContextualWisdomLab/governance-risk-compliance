"""Regression tests for the production-readiness evidence contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from cwl_grc.production_readiness import (
    ReadinessManifestError,
    load_manifest,
    main,
    readiness_summary,
    validate_manifest,
)


REPOSITORY = "ContextualWisdomLab/governance-risk-compliance"
ISSUE_PREFIX = f"https://github.com/{REPOSITORY}/issues/"


def _gate(
    *,
    gate_id: str = "identity-tenant-authorization",
    priority: str = "P0",
    status: str = "blocked",
    blockers: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": gate_id,
        "title": "Verified identity and tenant authorization",
        "priority": priority,
        "status": status,
        "owner": REPOSITORY,
        "issue_url": f"{ISSUE_PREFIX}4",
        "required_evidence": ["Authenticated cross-tenant regression evidence."],
        "blockers": ["Issue #4 is not complete."] if blockers is None else blockers,
        "evidence": [] if evidence is None else evidence,
    }


def _manifest(*gates: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "target": "production",
        "gates": list(gates or (_gate(),)),
    }


def _write_manifest(path: Path, manifest: object) -> None:
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_load_manifest_reads_json_object(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = _manifest()
    _write_manifest(path, manifest)

    assert load_manifest(path) == manifest


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        ("{", "is not valid JSON"),
        ("[]", "must contain a JSON object"),
    ],
)
def test_load_manifest_rejects_invalid_documents(
    tmp_path: Path,
    contents: str,
    expected: str,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ReadinessManifestError, match=expected):
        load_manifest(path)


def test_load_manifest_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReadinessManifestError, match="cannot be read"):
        load_manifest(tmp_path / "missing.json")


def test_validate_manifest_accepts_blocked_and_ready_gates() -> None:
    ready = _gate(
        gate_id="readiness-evidence-contract",
        status="ready",
        blockers=[],
        evidence=["cwl_grc/production_readiness.py"],
    )
    ready["issue_url"] = f"{ISSUE_PREFIX}15"

    gates = validate_manifest(_manifest(_gate(), ready))

    assert [gate["id"] for gate in gates] == [
        "identity-tenant-authorization",
        "readiness-evidence-contract",
    ]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda manifest: manifest.update(schema_version=2), "schema_version must be 1"),
        (lambda manifest: manifest.update(repository="other/repository"), "repository must be"),
        (lambda manifest: manifest.update(target="staging"), "target must be production"),
        (lambda manifest: manifest.update(gates="not-a-list"), "gates must be a non-empty list"),
        (lambda manifest: manifest.update(gates=[]), "gates must be a non-empty list"),
        (lambda manifest: manifest.update(gates=["not-an-object"]), r"gates\[0\] must be an object"),
    ],
)
def test_validate_manifest_rejects_invalid_top_level_contract(
    mutation: object,
    expected: str,
) -> None:
    manifest = _manifest()
    mutation(manifest)  # type: ignore[operator]

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", ["id", "title", "owner", "issue_url"])
def test_validate_manifest_requires_non_empty_gate_strings(field: str) -> None:
    manifest = _manifest()
    gate = manifest["gates"][0]  # type: ignore[index]
    gate[field] = "   "  # type: ignore[index]

    with pytest.raises(ReadinessManifestError, match=field):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("id", 7, "id must be a non-empty string"),
        ("priority", "P9", "priority must be one of"),
        ("status", "done", "status must be one of"),
        ("issue_url", "https://github.com/other/repository/issues/4", "canonical issue URL"),
        ("issue_url", ISSUE_PREFIX, "canonical issue URL"),
        ("issue_url", f"{ISSUE_PREFIX}not-a-number", "canonical issue URL"),
        ("required_evidence", "not-a-list", "required_evidence must be a list"),
        ("required_evidence", [], "required_evidence must not be empty"),
        ("required_evidence", [7], "required_evidence must contain non-empty strings"),
        ("required_evidence", [""], "required_evidence must contain non-empty strings"),
        ("blockers", "not-a-list", "blockers must be a list"),
        ("blockers", [""], "blockers must contain non-empty strings"),
        ("evidence", "not-a-list", "evidence must be a list"),
        ("evidence", [""], "evidence must contain non-empty strings"),
    ],
)
def test_validate_manifest_rejects_invalid_gate_fields(
    field: str,
    value: object,
    expected: str,
) -> None:
    manifest = _manifest()
    gate = manifest["gates"][0]  # type: ignore[index]
    gate[field] = value  # type: ignore[index]

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


def test_validate_manifest_rejects_duplicate_gate_ids() -> None:
    duplicate = deepcopy(_gate())
    duplicate["issue_url"] = f"{ISSUE_PREFIX}8"

    with pytest.raises(ReadinessManifestError, match="duplicate gate id"):
        validate_manifest(_manifest(_gate(), duplicate))


@pytest.mark.parametrize("status", ["blocked", "in_progress"])
def test_validate_manifest_requires_blockers_for_non_ready_gate(status: str) -> None:
    gate = _gate(status=status, blockers=[])

    with pytest.raises(ReadinessManifestError, match="must name at least one blocker"):
        validate_manifest(_manifest(gate))


def test_validate_manifest_rejects_ready_gate_with_blockers() -> None:
    gate = _gate(status="ready", evidence=["tests passed"])

    with pytest.raises(ReadinessManifestError, match="ready gate must not have blockers"):
        validate_manifest(_manifest(gate))


def test_validate_manifest_rejects_ready_gate_without_evidence() -> None:
    gate = _gate(status="ready", blockers=[], evidence=[])

    with pytest.raises(ReadinessManifestError, match="ready gate must name concrete evidence"):
        validate_manifest(_manifest(gate))


def test_readiness_summary_lists_every_blocking_gate() -> None:
    blocked = _gate()
    in_progress = _gate(
        gate_id="postgresql-lifecycle",
        priority="P0",
        status="in_progress",
        blockers=["Issue #8 is still open."],
    )
    in_progress["issue_url"] = f"{ISSUE_PREFIX}8"
    ready = _gate(
        gate_id="readiness-evidence-contract",
        status="ready",
        blockers=[],
        evidence=["validator"],
    )
    ready["issue_url"] = f"{ISSUE_PREFIX}15"

    summary = readiness_summary(validate_manifest(_manifest(blocked, in_progress, ready)))

    assert summary == {
        "production_ready": False,
        "gate_count": 3,
        "ready_gate_count": 1,
        "blocking_gates": [
            {
                "id": "identity-tenant-authorization",
                "priority": "P0",
                "status": "blocked",
                "issue_url": f"{ISSUE_PREFIX}4",
                "blockers": ["Issue #4 is not complete."],
            },
            {
                "id": "postgresql-lifecycle",
                "priority": "P0",
                "status": "in_progress",
                "issue_url": f"{ISSUE_PREFIX}8",
                "blockers": ["Issue #8 is still open."],
            },
        ],
    }


def test_readiness_summary_reports_all_ready() -> None:
    ready = _gate(status="ready", blockers=[], evidence=["verified"])

    assert readiness_summary(validate_manifest(_manifest(ready))) == {
        "production_ready": True,
        "gate_count": 1,
        "ready_gate_count": 1,
        "blocking_gates": [],
    }


def test_main_validates_blocked_manifest_without_certifying_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    _write_manifest(path, _manifest())

    assert main([str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["production_ready"] is False


def test_main_require_ready_fails_for_blocked_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    _write_manifest(path, _manifest())

    assert main([str(path), "--require-ready"]) == 1
    assert json.loads(capsys.readouterr().out)["blocking_gates"]


def test_main_require_ready_accepts_fully_evidenced_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    ready = _gate(status="ready", blockers=[], evidence=["verified"])
    _write_manifest(path, _manifest(ready))

    assert main([str(path), "--require-ready"]) == 0
    assert json.loads(capsys.readouterr().out)["production_ready"] is True


def test_main_returns_machine_readable_validation_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{", encoding="utf-8")

    assert main([str(path)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "error": f"Readiness manifest {path} is not valid JSON.",
        "valid": False,
    }
