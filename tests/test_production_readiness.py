"""Regression tests for the production-readiness evidence contract."""

from __future__ import annotations

import hashlib
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
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "production" / "production-readiness.json"
DEFAULT_EVIDENCE_PATH = "tests/test_production_readiness.py"


def _sha256(contents: bytes) -> str:
    """Return the SHA-256 digest for exact contents."""
    return hashlib.sha256(contents).hexdigest()


def _evidence(
    *,
    path: str = DEFAULT_EVIDENCE_PATH,
    digest: str | None = None,
) -> dict[str, str]:
    """Return one canonical repository-file evidence binding."""
    evidence_file = REPOSITORY_ROOT / path
    return {
        "kind": "repository_file",
        "path": path,
        "sha256": digest or _sha256(evidence_file.read_bytes()),
    }


def _gate(
    *,
    gate_id: str = "identity-tenant-authorization",
    priority: str = "P0",
    status: str = "blocked",
    blockers: list[str] | None = None,
    evidence: list[object] | None = None,
) -> dict[str, object]:
    """Return one test gate with the canonical repository ownership contract."""
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
    """Return the canonical manifest or a focused supplied gate list."""
    if not gates:
        return deepcopy(load_manifest(MANIFEST_PATH))
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "target": "production",
        "gates": list(gates),
    }


def _write_manifest(path: Path, manifest: object) -> None:
    """Write one JSON manifest used by the command contract."""
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_load_manifest_reads_json_object(tmp_path: Path) -> None:
    """The loader returns an exact JSON object."""
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
    """Malformed JSON and non-object roots fail closed."""
    path = tmp_path / "manifest.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ReadinessManifestError, match=expected):
        load_manifest(path)


def test_load_manifest_reports_missing_file(tmp_path: Path) -> None:
    """A missing manifest is an explicit validation error."""
    with pytest.raises(ReadinessManifestError, match="cannot be read"):
        load_manifest(tmp_path / "missing.json")


def test_validate_manifest_accepts_blocked_and_ready_gates() -> None:
    """The committed closed gate set is structurally valid."""
    gates = validate_manifest(_manifest())

    assert [gate["id"] for gate in gates] == [
        "identity-tenant-authorization",
        "postgresql-lifecycle",
        "evidence-lifecycle-recovery",
        "release-artifact-provenance",
        "operability-observability",
        "api-contract",
        "risk-management",
        "audit-management",
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
    """Top-level repository and gate-set authority is closed."""
    manifest = _manifest()
    mutation(manifest)  # type: ignore[operator]

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", ["id", "title", "owner", "issue_url"])
def test_validate_manifest_requires_non_empty_gate_strings(field: str) -> None:
    """Gate identity fields reject blank or normalized values."""
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
        ("evidence", ["verified"], "must contain evidence objects"),
    ],
)
def test_validate_manifest_rejects_invalid_gate_fields(
    field: str,
    value: object,
    expected: str,
) -> None:
    """Gate fields retain exact types and canonical formats."""
    manifest = _manifest()
    gate = manifest["gates"][0]  # type: ignore[index]
    gate[field] = value  # type: ignore[index]

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ({}, "exactly kind, path, and sha256"),
        (
            {
                "kind": "note",
                "path": DEFAULT_EVIDENCE_PATH,
                "sha256": "0" * 64,
            },
            "kind must be repository_file",
        ),
        (
            {
                "kind": "repository_file",
                "path": "../outside.txt",
                "sha256": "0" * 64,
            },
            "canonical repository-relative path",
        ),
        (
            {
                "kind": "repository_file",
                "path": DEFAULT_EVIDENCE_PATH,
                "sha256": "ABCDEF",
            },
            "64 lowercase hexadecimal",
        ),
    ],
)
def test_validate_manifest_rejects_invalid_evidence_objects(
    evidence: dict[str, object],
    expected: str,
) -> None:
    """Evidence objects are closed to exact repository paths and SHA-256 digests."""
    manifest = _manifest()
    gate = manifest["gates"][0]  # type: ignore[index]
    gate["evidence"] = [evidence]  # type: ignore[index]

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


def test_validate_manifest_rejects_duplicate_evidence_paths() -> None:
    """One path cannot be listed repeatedly to inflate evidence volume."""
    manifest = _manifest()
    gate = manifest["gates"][0]  # type: ignore[index]
    gate["evidence"] = [_evidence(), _evidence()]  # type: ignore[index]

    with pytest.raises(ReadinessManifestError, match="duplicate repository path"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_duplicate_gate_ids() -> None:
    """A gate ID has exactly one canonical issue and state."""
    duplicate = deepcopy(_gate())
    duplicate["issue_url"] = f"{ISSUE_PREFIX}8"

    with pytest.raises(ReadinessManifestError, match="duplicate gate id"):
        validate_manifest(_manifest(_gate(), duplicate))


@pytest.mark.parametrize("status", ["blocked", "in_progress"])
def test_validate_manifest_requires_blockers_for_non_ready_gate(status: str) -> None:
    """Every non-ready gate states why it cannot certify production."""
    gate = _gate(status=status, blockers=[])

    with pytest.raises(ReadinessManifestError, match="must name at least one blocker"):
        validate_manifest(_manifest(gate))


def test_validate_manifest_rejects_ready_gate_with_blockers() -> None:
    """A ready gate cannot retain contradictory blocker evidence."""
    gate = _gate(status="ready", evidence=[_evidence()])

    with pytest.raises(ReadinessManifestError, match="ready gate must not have blockers"):
        validate_manifest(_manifest(gate))


def test_validate_manifest_rejects_ready_gate_without_evidence() -> None:
    """A ready gate requires at least one SHA-256-bound evidence file."""
    gate = _gate(status="ready", blockers=[], evidence=[])

    with pytest.raises(ReadinessManifestError, match="ready gate must name concrete evidence"):
        validate_manifest(_manifest(gate))


def test_readiness_summary_lists_every_blocking_gate() -> None:
    """The summary preserves every blocker instead of collapsing the queue."""
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
        evidence=[_evidence()],
    )
    ready["issue_url"] = f"{ISSUE_PREFIX}15"

    summary = readiness_summary([blocked, in_progress, ready])

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
    """A fully ready set has no hidden blocking gate."""
    ready = _gate(status="ready", blockers=[], evidence=[_evidence()])

    assert readiness_summary([ready]) == {
        "production_ready": True,
        "gate_count": 1,
        "ready_gate_count": 1,
        "blocking_gates": [],
    }


def test_main_validates_blocked_manifest_without_certifying_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ordinary validation can describe blockers without claiming readiness."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _manifest())

    assert main([str(path), "--repository-root", str(REPOSITORY_ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["production_ready"] is False


def test_main_require_ready_fails_for_blocked_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Release mode remains non-zero while any validated gate is blocked."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _manifest())

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 1
    assert json.loads(capsys.readouterr().out)["blocking_gates"]


def test_main_require_ready_accepts_fully_evidenced_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Release mode succeeds only with SHA-256-bound evidence for every gate."""
    path = tmp_path / "manifest.json"
    manifest = _manifest()
    gates = manifest["gates"]
    assert isinstance(gates, list)
    for gate in gates:
        assert isinstance(gate, dict)
        gate["status"] = "ready"
        gate["blockers"] = []
        gate["evidence"] = [_evidence()]
    _write_manifest(path, manifest)

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["production_ready"] is True


def test_main_returns_machine_readable_validation_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed manifests return deterministic machine-readable errors."""
    path = tmp_path / "manifest.json"
    path.write_text("{", encoding="utf-8")

    assert main([str(path), "--repository-root", str(REPOSITORY_ROOT)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "error": f"Readiness manifest {path} is not valid JSON.",
        "valid": False,
    }
