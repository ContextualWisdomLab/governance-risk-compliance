"""Validate the versioned production-readiness evidence contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any


EXPECTED_REPOSITORY = "ContextualWisdomLab/governance-risk-compliance"
EXPECTED_SCHEMA_VERSION = 1
EXPECTED_TARGET = "production"
ISSUE_URL_PREFIX = f"https://github.com/{EXPECTED_REPOSITORY}/issues/"
ALLOWED_PRIORITIES = frozenset({"P0", "P1", "P2"})
ALLOWED_STATUSES = frozenset({"blocked", "in_progress", "ready"})
REPOSITORY_FILE_EVIDENCE = "repository_file"
REPOSITORY_FILE_FIELDS = frozenset({"kind", "path", "sha256"})
READINESS_EVIDENCE_INDEX_PATH = "docs/production/readiness-evidence-index.json"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIRED_GATE_CONTRACTS = {
    "identity-tenant-authorization": ("P0", 4),
    "postgresql-lifecycle": ("P0", 8),
    "evidence-lifecycle-recovery": ("P0", 9),
    "release-artifact-provenance": ("P0", 10),
    "operability-observability": ("P0", 11),
    "api-contract": ("P1", 12),
    "risk-management": ("P1", 13),
    "audit-management": ("P1", 14),
    "readiness-evidence-contract": ("P0", 15),
}


class ReadinessManifestError(ValueError):
    """Report a malformed or internally inconsistent readiness manifest."""


def load_manifest(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON readiness manifest from ``path``."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReadinessManifestError(f"Readiness manifest {path} cannot be read.") from exc
    try:
        manifest = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise ReadinessManifestError(
            f"Readiness manifest {path} is not valid JSON."
        ) from exc
    if not isinstance(manifest, dict):
        raise ReadinessManifestError("Readiness manifest must contain a JSON object.")
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate ``manifest`` and return its ordered production gates."""
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ReadinessManifestError(
            f"schema_version must be {EXPECTED_SCHEMA_VERSION}."
        )
    if manifest.get("repository") != EXPECTED_REPOSITORY:
        raise ReadinessManifestError(f"repository must be {EXPECTED_REPOSITORY}.")
    if manifest.get("target") != EXPECTED_TARGET:
        raise ReadinessManifestError(f"target must be {EXPECTED_TARGET}.")

    gates = manifest.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ReadinessManifestError("gates must be a non-empty list.")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(gates):
        path = f"gates[{index}]"
        if not isinstance(candidate, dict):
            raise ReadinessManifestError(f"{path} must be an object.")
        gate = candidate
        gate_id = _require_string(gate, "id", path)
        _require_string(gate, "title", path)
        priority = _require_string(gate, "priority", path)
        status = _require_string(gate, "status", path)
        owner = _require_string(gate, "owner", path)
        issue_url = _require_string(gate, "issue_url", path)
        _require_string_list(
            gate,
            "required_evidence",
            path,
            allow_empty=False,
        )
        blockers = _require_string_list(gate, "blockers", path, allow_empty=True)
        evidence = _require_evidence_list(gate, path)

        if gate_id in seen_ids:
            raise ReadinessManifestError(f"duplicate gate id: {gate_id}.")
        seen_ids.add(gate_id)
        if priority not in ALLOWED_PRIORITIES:
            allowed = ", ".join(sorted(ALLOWED_PRIORITIES))
            raise ReadinessManifestError(f"{path}.priority must be one of: {allowed}.")
        if status not in ALLOWED_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_STATUSES))
            raise ReadinessManifestError(f"{path}.status must be one of: {allowed}.")
        if owner != EXPECTED_REPOSITORY:
            raise ReadinessManifestError(f"{path}.owner must be {EXPECTED_REPOSITORY}.")
        if not _is_canonical_issue_url(issue_url):
            raise ReadinessManifestError(
                f"{path}.issue_url must be a canonical issue URL for {EXPECTED_REPOSITORY}."
            )
        if status == "ready":
            if blockers:
                raise ReadinessManifestError(f"{path}: ready gate must not have blockers.")
            if not evidence:
                raise ReadinessManifestError(
                    f"{path}: ready gate must name concrete evidence."
                )
        elif not blockers:
            raise ReadinessManifestError(
                f"{path}: {status} gate must name at least one blocker."
            )

        validated.append(gate)

    required_ids = set(REQUIRED_GATE_CONTRACTS)
    missing_ids = required_ids - seen_ids
    if missing_ids:
        missing = ", ".join(sorted(missing_ids))
        raise ReadinessManifestError(f"missing required gate ids: {missing}.")
    unexpected_ids = seen_ids - required_ids
    if unexpected_ids:
        unexpected = ", ".join(sorted(unexpected_ids))
        raise ReadinessManifestError(f"unexpected gate ids: {unexpected}.")

    for index, gate in enumerate(validated):
        path = f"gates[{index}]"
        gate_id = gate["id"]
        expected_priority, issue_number = REQUIRED_GATE_CONTRACTS[gate_id]
        if gate["priority"] != expected_priority:
            raise ReadinessManifestError(
                f"{path}.priority must be {expected_priority} for required gate {gate_id}."
            )
        expected_issue_url = f"{ISSUE_URL_PREFIX}{issue_number}"
        if gate["issue_url"] != expected_issue_url:
            raise ReadinessManifestError(
                f"{path}.issue_url must be {expected_issue_url} for required gate {gate_id}."
            )
    return validated


def verify_repository_evidence(
    gates: Sequence[dict[str, Any]],
    repository_root: Path,
) -> None:
    """Verify every evidence path and SHA-256 digest in one reviewed tree."""
    try:
        root = repository_root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ReadinessManifestError(
            f"Repository root {repository_root} cannot be resolved."
        ) from exc
    if not root.is_dir():
        raise ReadinessManifestError(f"Repository root {root} must be a directory.")

    for gate_index, gate in enumerate(gates):
        for evidence_index, evidence in enumerate(gate["evidence"]):
            path = f"gates[{gate_index}].evidence[{evidence_index}]"
            candidate = root / evidence["path"]
            try:
                resolved = candidate.resolve(strict=True)
            except (OSError, ValueError) as exc:
                raise ReadinessManifestError(
                    f"{path}.path does not identify a readable repository file."
                ) from exc
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ReadinessManifestError(
                    f"{path}.path escapes the repository root."
                ) from exc
            if not resolved.is_file():
                raise ReadinessManifestError(
                    f"{path}.path must identify a regular repository file."
                )
            try:
                contents = resolved.read_bytes()
            except OSError as exc:
                raise ReadinessManifestError(
                    f"{path}.path cannot be read for SHA-256 verification."
                ) from exc
            if _sha256(contents) != evidence["sha256"]:
                raise ReadinessManifestError(
                    f"{path}.sha256 does not match the repository file."
                )
            if evidence["path"] == READINESS_EVIDENCE_INDEX_PATH:
                _verify_readiness_evidence_index(contents, root, path)


def _verify_readiness_evidence_index(
    contents: bytes,
    repository_root: Path,
    evidence_path: str,
) -> None:
    """Verify the Git blob coordinates recorded by the readiness index."""
    try:
        index = json.loads(contents)
        components = index["components"]
        if not isinstance(components, list) or not components:
            raise ValueError("components must be a non-empty list")
        for component in components:
            component_path = component["path"]
            expected_oid = component["git_blob_oid"]
            resolved = (repository_root / component_path).resolve(strict=True)
            resolved.relative_to(repository_root)
            actual_oid = _git_blob_oid(resolved.read_bytes())
            if actual_oid != expected_oid:
                raise ReadinessManifestError(
                    f"{evidence_path} records a stale Git blob ID for {component_path}."
                )
    except ReadinessManifestError:
        raise
    except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError) as exc:
        raise ReadinessManifestError(
            f"{evidence_path} is not a valid readiness evidence index."
        ) from exc


def _git_blob_oid(contents: bytes) -> str:
    """Return Git's SHA-1 content coordinate, not a security digest."""
    header = f"blob {len(contents)}\0".encode("ascii")
    return hashlib.new("sha1", header + contents, usedforsecurity=False).hexdigest()


def readiness_summary(gates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return a deterministic readiness result for validated ``gates``."""
    blocking_gates: list[dict[str, Any]] = []
    ready_gate_count = 0
    for gate in gates:
        if gate["status"] == "ready":
            ready_gate_count += 1
        else:
            blocking_gates.append(
                {
                    "id": gate["id"],
                    "priority": gate["priority"],
                    "status": gate["status"],
                    "issue_url": gate["issue_url"],
                    "blockers": gate["blockers"],
                }
            )
    return {
        "production_ready": not blocking_gates,
        "gate_count": len(gates),
        "ready_gate_count": ready_gate_count,
        "blocking_gates": blocking_gates,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a manifest and optionally require every production gate to be ready."""
    parser = argparse.ArgumentParser(
        prog="cwl-grc-production-readiness",
        description="Validate the CWL GRC production-readiness evidence contract.",
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository tree used to verify evidence paths and SHA-256 digests.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 1 while any validated production gate is not ready.",
    )
    args = parser.parse_args(argv)
    try:
        gates = validate_manifest(load_manifest(args.manifest))
        verify_repository_evidence(gates, args.repository_root)
    except ReadinessManifestError as exc:
        print(json.dumps({"error": str(exc), "valid": False}, sort_keys=True))
        return 2

    summary = readiness_summary(gates)
    summary["valid"] = True
    print(json.dumps(summary, sort_keys=True))
    if args.require_ready and not summary["production_ready"]:
        return 1
    return 0


def _require_string(gate: dict[str, Any], field: str, path: str) -> str:
    """Return one required non-empty string field from a gate or evidence object."""
    value = gate.get(field)
    if not isinstance(value, str):
        raise ReadinessManifestError(f"{path}.{field} must be a non-empty string.")
    normalized = value.strip()
    if not normalized:
        raise ReadinessManifestError(f"{path}.{field} must be a non-empty string.")
    if normalized != value:
        raise ReadinessManifestError(
            f"{path}.{field} must not contain surrounding whitespace."
        )
    return value


def _require_string_list(
    gate: dict[str, Any],
    field: str,
    path: str,
    *,
    allow_empty: bool,
) -> list[str]:
    """Return one required list of non-empty strings from a gate."""
    value = gate.get(field)
    if not isinstance(value, list):
        raise ReadinessManifestError(f"{path}.{field} must be a list.")
    if not allow_empty and not value:
        raise ReadinessManifestError(f"{path}.{field} must not be empty.")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ReadinessManifestError(
                f"{path}.{field} must contain non-empty strings."
            )
        text = item.strip()
        if not text:
            raise ReadinessManifestError(
                f"{path}.{field} must contain non-empty strings."
            )
        if text != item:
            raise ReadinessManifestError(
                f"{path}.{field} must not contain surrounding whitespace."
            )
        normalized.append(item)
    return normalized


def _require_evidence_list(
    gate: dict[str, Any],
    path: str,
) -> list[dict[str, str]]:
    """Return canonical repository-file evidence objects bound with SHA-256."""
    value = gate.get("evidence")
    if not isinstance(value, list):
        raise ReadinessManifestError(f"{path}.evidence must be a list.")
    validated: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(value):
        evidence_path = f"{path}.evidence[{index}]"
        if not isinstance(item, dict):
            raise ReadinessManifestError(
                f"{path}.evidence must contain evidence objects."
            )
        if set(item) != REPOSITORY_FILE_FIELDS:
            raise ReadinessManifestError(
                f"{evidence_path} must contain exactly kind, path, and sha256."
            )
        kind = _require_string(item, "kind", evidence_path)
        if kind != REPOSITORY_FILE_EVIDENCE:
            raise ReadinessManifestError(
                f"{evidence_path}.kind must be {REPOSITORY_FILE_EVIDENCE}."
            )
        repository_path = _require_string(item, "path", evidence_path)
        if not _is_canonical_repository_path(repository_path):
            raise ReadinessManifestError(
                f"{evidence_path}.path must be a canonical repository-relative path."
            )
        digest = _require_string(item, "sha256", evidence_path)
        if SHA256_PATTERN.fullmatch(digest) is None:
            raise ReadinessManifestError(
                f"{evidence_path}.sha256 must be 64 lowercase hexadecimal characters."
            )
        if repository_path in seen_paths:
            raise ReadinessManifestError(
                f"{path}.evidence has duplicate repository path: {repository_path}."
            )
        seen_paths.add(repository_path)
        validated.append(
            {
                "kind": kind,
                "path": repository_path,
                "sha256": digest,
            }
        )
    return validated


def _is_canonical_repository_path(value: str) -> bool:
    """Return whether ``value`` is one unambiguous path inside a repository tree."""
    if "\\" in value:
        return False
    candidate = PurePosixPath(value)
    return (
        not candidate.is_absolute()
        and bool(candidate.parts)
        and candidate.parts[0] != ".git"
        and all(part not in {".", ".."} for part in candidate.parts)
        and candidate.as_posix() == value
    )


def _sha256(contents: bytes) -> str:
    """Return the SHA-256 digest for exact ``contents``."""
    return hashlib.sha256(contents).hexdigest()


def _is_canonical_issue_url(value: str) -> bool:
    """Return whether ``value`` is a canonical issue URL for this repository."""
    if not value.startswith(ISSUE_URL_PREFIX):
        return False
    issue_number = value.removeprefix(ISSUE_URL_PREFIX)
    return bool(issue_number) and issue_number.isdigit()
