"""Fail-closed regressions for production-readiness evidence bindings."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

import cwl_grc.production_readiness as production_readiness
from cwl_grc.production_readiness import load_manifest, main


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "docs/production/production-readiness.json"
EVIDENCE_PATH = "tests/test_production_readiness_evidence_binding.py"
INDEX_PATH = "docs/production/readiness-evidence-index.json"


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


def _sha256(contents: bytes) -> str:
    """Return the SHA-256 digest for exact contents."""
    return hashlib.sha256(contents).hexdigest()


def _bound_repository_evidence(*, digest: str | None = None) -> dict[str, str]:
    """Return one repository-file evidence reference bound to exact content."""
    source = REPOSITORY_ROOT / EVIDENCE_PATH
    return {
        "kind": "repository_file",
        "path": EVIDENCE_PATH,
        "sha256": digest or _sha256(source.read_bytes()),
    }


def _bound_index_evidence() -> dict[str, str]:
    """Return the committed readiness index bound to its exact bytes."""
    source = REPOSITORY_ROOT / INDEX_PATH
    return {
        "kind": "repository_file",
        "path": INDEX_PATH,
        "sha256": _sha256(source.read_bytes()),
    }


def _main_arguments(manifest_path: Path, repository_root: Path) -> list[str]:
    """Return release-mode CLI arguments for one manifest and repository tree."""
    return [
        str(manifest_path),
        "--repository-root",
        str(repository_root),
        "--require-ready",
    ]


def test_release_mode_rejects_opaque_success_words_as_evidence(
    tmp_path: Path,
) -> None:
    """An arbitrary success-shaped string cannot certify every production gate."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest(["verified"]))

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2


def test_release_mode_accepts_hash_bound_repository_file_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical repository file with its exact SHA-256 digest is verifiable."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest([_bound_repository_evidence()]))
    opened_flags: list[int] = []
    real_open = production_readiness.os.open

    def capture_open(file_path: Path, flags: int) -> int:
        opened_flags.append(flags)
        return real_open(file_path, flags)

    monkeypatch.setattr(production_readiness.os, "open", capture_open)

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 0
    assert opened_flags
    assert all(flags & os.O_NOFOLLOW for flags in opened_flags)


def test_release_mode_accepts_current_readiness_index_component_oids(
    tmp_path: Path,
) -> None:
    """The readiness index must point at the exact current component blobs."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest([_bound_index_evidence()]))

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 0


def test_release_mode_rejects_stale_readiness_index_component_oid(
    tmp_path: Path,
) -> None:
    """A stale component coordinate cannot certify the readiness index."""
    path = tmp_path / "manifest.json"
    root = tmp_path / "repository"
    root.mkdir()
    component = root / "component.py"
    component.write_text("print('current')\n", encoding="utf-8")
    index_path = root / INDEX_PATH
    index_path.parent.mkdir(parents=True)
    index_path.write_text(
        json.dumps(
            {
                "components": [
                    {"path": "component.py", "git_blob_oid": "0" * 40},
                ]
            }
        ),
        encoding="utf-8",
    )
    evidence = {
        "kind": "repository_file",
        "path": INDEX_PATH,
        "sha256": _sha256(index_path.read_bytes()),
    }
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_malformed_readiness_index(tmp_path: Path) -> None:
    """A malformed readiness index fails closed before it can certify components."""
    root = tmp_path / "repository"
    index_path = root / INDEX_PATH
    index_path.parent.mkdir(parents=True)
    index_path.write_text('{"components": []}', encoding="utf-8")
    path = tmp_path / "manifest.json"
    evidence = {
        "kind": "repository_file",
        "path": INDEX_PATH,
        "sha256": _sha256(index_path.read_bytes()),
    }
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_wrong_repository_file_digest(
    tmp_path: Path,
) -> None:
    """A path cannot certify readiness after its reviewed content changes."""
    path = tmp_path / "manifest.json"
    _write_manifest(
        path,
        _all_ready_manifest([_bound_repository_evidence(digest="0" * 64)]),
    )

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2


def test_release_mode_rejects_repository_path_escape(
    tmp_path: Path,
) -> None:
    """Evidence paths cannot traverse outside the reviewed repository tree."""
    path = tmp_path / "manifest.json"
    evidence = _bound_repository_evidence()
    evidence["path"] = "../outside.txt"
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2


def test_release_mode_rejects_backslash_repository_path(
    tmp_path: Path,
) -> None:
    """Platform-dependent backslash paths cannot alter repository evidence meaning."""
    path = tmp_path / "manifest.json"
    evidence = _bound_repository_evidence()
    evidence["path"] = r"tests\evidence.py"
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2


def test_release_mode_rejects_embedded_null_repository_path(
    tmp_path: Path,
) -> None:
    """A path rejected by the OS remains a typed manifest validation error."""
    path = tmp_path / "manifest.json"
    evidence = _bound_repository_evidence()
    evidence["path"] = "tests/\u0000evidence.py"
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2


def test_release_mode_rejects_missing_repository_root(tmp_path: Path) -> None:
    """Evidence verification fails when the reviewed repository tree is absent."""
    path = tmp_path / "manifest.json"
    _write_manifest(path, _all_ready_manifest([_bound_repository_evidence()]))

    assert main(_main_arguments(path, tmp_path / "missing-root")) == 2


def test_release_mode_rejects_non_directory_repository_root(tmp_path: Path) -> None:
    """A regular file cannot serve as the repository evidence authority."""
    path = tmp_path / "manifest.json"
    root = tmp_path / "not-a-directory"
    root.write_text("not a repository", encoding="utf-8")
    _write_manifest(path, _all_ready_manifest([_bound_repository_evidence()]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_missing_repository_evidence_file(
    tmp_path: Path,
) -> None:
    """A syntactically valid locator cannot certify a file that is absent."""
    path = tmp_path / "manifest.json"
    root = tmp_path / "repository"
    root.mkdir()
    evidence = {
        "kind": "repository_file",
        "path": "missing.txt",
        "sha256": "0" * 64,
    }
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_evidence_symlink_escape(tmp_path: Path) -> None:
    """A repository path cannot redirect evidence verification outside the tree."""
    path = tmp_path / "manifest.json"
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside evidence", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)
    evidence = {
        "kind": "repository_file",
        "path": "escape.txt",
        "sha256": _sha256(outside.read_bytes()),
    }
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_directory_as_evidence(tmp_path: Path) -> None:
    """Only regular repository files can become readiness evidence."""
    path = tmp_path / "manifest.json"
    root = tmp_path / "repository"
    (root / "evidence").mkdir(parents=True)
    evidence = {
        "kind": "repository_file",
        "path": "evidence",
        "sha256": "0" * 64,
    }
    _write_manifest(path, _all_ready_manifest([evidence]))

    assert main(_main_arguments(path, root)) == 2


def test_release_mode_rejects_unreadable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file read failure is a typed non-passing evidence condition."""
    path = tmp_path / "manifest.json"
    evidence = _bound_repository_evidence()
    _write_manifest(path, _all_ready_manifest([evidence]))

    def fail_open(_path: Path, _flags: int) -> int:
        raise OSError("simulated read failure")

    monkeypatch.setattr(production_readiness.os, "open", fail_open)
    assert main(_main_arguments(path, REPOSITORY_ROOT)) == 2
