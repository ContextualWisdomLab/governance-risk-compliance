"""Prove that production-readiness release gates remain complete and exact."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cwl_grc.production_readiness import (
    ReadinessManifestError,
    load_manifest,
    validate_manifest,
)


REPOSITORY = "ContextualWisdomLab/governance-risk-compliance"
ISSUE_PREFIX = f"https://github.com/{REPOSITORY}/issues/"
MANIFEST_PATH = (
    Path(__file__).parents[1] / "docs" / "production" / "production-readiness.json"
)


def _committed_manifest() -> dict[str, object]:
    return deepcopy(load_manifest(MANIFEST_PATH))


def _first_gate(manifest: dict[str, object]) -> dict[str, object]:
    gates = manifest["gates"]
    assert isinstance(gates, list)
    gate = gates[0]
    assert isinstance(gate, dict)
    return gate


def test_validate_manifest_rejects_missing_required_gate() -> None:
    manifest = _committed_manifest()
    gates = manifest["gates"]
    assert isinstance(gates, list)
    removed = gates.pop()
    assert isinstance(removed, dict)

    with pytest.raises(
        ReadinessManifestError,
        match=rf"missing required gate.*{removed['id']}",
    ):
        validate_manifest(manifest)


def test_validate_manifest_rejects_unexpected_gate() -> None:
    manifest = _committed_manifest()
    gates = manifest["gates"]
    assert isinstance(gates, list)
    extra = deepcopy(_first_gate(manifest))
    extra["id"] = "unreviewed-release-bypass"
    extra["title"] = "Unreviewed release bypass"
    extra["issue_url"] = f"{ISSUE_PREFIX}999"
    gates.append(extra)

    with pytest.raises(
        ReadinessManifestError,
        match="unexpected gate.*unreviewed-release-bypass",
    ):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("owner", "ContextualWisdomLab/other", "owner must be"),
        ("priority", "P1", "priority must be P0"),
        ("issue_url", f"{ISSUE_PREFIX}8", rf"issue_url must be .*issues/4"),
    ],
)
def test_validate_manifest_rejects_required_gate_mapping_changes(
    field: str,
    value: str,
    expected: str,
) -> None:
    manifest = _committed_manifest()
    _first_gate(manifest)[field] = value

    with pytest.raises(ReadinessManifestError, match=expected):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", " identity-tenant-authorization"),
        ("status", "in_progress "),
    ],
)
def test_validate_manifest_rejects_surrounding_gate_whitespace(
    field: str,
    value: str,
) -> None:
    manifest = _committed_manifest()
    _first_gate(manifest)[field] = value

    with pytest.raises(ReadinessManifestError, match="surrounding whitespace"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_surrounding_evidence_whitespace() -> None:
    manifest = _committed_manifest()
    _first_gate(manifest)["required_evidence"] = [" evidence must be exact"]

    with pytest.raises(ReadinessManifestError, match="surrounding whitespace"):
        validate_manifest(manifest)
