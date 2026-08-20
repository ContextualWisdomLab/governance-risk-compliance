"""Fail-closed regressions for production-readiness evidence bindings."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from cwl_grc.production_readiness import load_manifest, main


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "docs/production/production-readiness.json"
EVIDENCE_PATH = "tests/test_production_readiness_evidence_binding.py"


def _all_ready_manifest(evidence: list[object]) -> dict[str, object]:
    """Return the canonical gate set marked ready with the supplied evidence."""
    manifest = deepcopy(load_manifest(MANIFEST_PATH))
    gates = manifest["gates"]
    assert isinstance(gates, list)
    for gate in gates:
        assert isinstance(gate, dict)
        gate["status"] = "ready"
        gate["blockers"] = []
        gate["evidence"] = deepcopy(evidence)
    return manifest


def _write_manifest(path: Path, manifest: object) -> None:
    """Write one deterministic JSON manifest for CLI validation."""
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _git_blob_sha(contents: bytes) -> str:
    """Return the repository-native Git object identity for exact contents."""
    header = f"blob {len(contents)}\0".encode("ascii")
    return hashlib.sha1(header + contents, usedforsecurity=False).hexdigest()


def _bound_repository_evidence(*, blob_sha: str | None = None) -> dict[str, str]:
    """Return one repository-file evidence reference bound to exact content."""
    source = REPOSITORY_ROOT / EVIDENCE_PATH
    return {
        "kind": "repository_file",
        "path": EVIDENCE_PATH,
        "git_blob_sha": blob_sha or _git_blob_sha(source.read_bytes()),
    }


def test_release_mode_rejects_opaque_success_words_as_evidence(
    tmp_path: Path,
) -> None:
    """An arbitrary success-shaped string cannot certify every production gate."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest(["verified"]))

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 2


def test_release_mode_accepts_hash_bound_repository_file_evidence(
    tmp_path: Path,
) -> None:
    """A canonical repository file with its exact Git blob identity is verifiable."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest([_bound_repository_evidence()]))

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 0


def test_release_mode_rejects_wrong_repository_file_digest(
    tmp_path: Path,
) -> None:
    """A path cannot certify readiness after its reviewed content changes."""
    path = tmp_path / "manifest.json"
    _write_manifest(
        path,
        _all_ready_manifest([_bound_repository_evidence(blob_sha="0" * 40)]),
    )

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 2


def test_release_mode_rejects_repository_path_escape(
    tmp_path: Path,
) -> None:
    """Evidence paths cannot traverse outside the reviewed repository tree."""
    path = tmp_path / "manifest.json"
    evidence = _bound_repository_evidence()
    evidence["path"] = "../outside.txt"
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(
        [
            str(path),
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--require-ready",
        ]
    ) == 2
