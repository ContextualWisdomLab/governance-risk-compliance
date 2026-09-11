"""Regression coverage for operator-facing HTTP serve startup failures."""

from __future__ import annotations

import json

import pytest

from cwl_grc.cli import main as cli_main
from cwl_grc.database import (
    SCHEMA_AHEAD_RECOVERY,
    SCHEMA_MIGRATION_RECOVERY,
    SchemaCompatibilityError,
)


@pytest.mark.parametrize(
    ("recovery_action", "expected_next_action"),
    [
        (SCHEMA_MIGRATION_RECOVERY, SCHEMA_MIGRATION_RECOVERY),
        (SCHEMA_AHEAD_RECOVERY, SCHEMA_AHEAD_RECOVERY),
    ],
)
def test_serve_reports_the_schema_state_recovery_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    recovery_action: str,
    expected_next_action: str,
) -> None:
    """Return actionable JSON that matches the reported schema state, not a fixed command."""

    def fail_startup() -> None:
        raise SchemaCompatibilityError(
            "The stored GRC schema is incompatible with this build.",
            recovery_action=recovery_action,
        )

    monkeypatch.setattr("cwl_grc.cli.create_app", fail_startup)

    assert cli_main(["serve"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "error": "The stored GRC schema is incompatible with this build.",
        "next_action": expected_next_action,
    }


def test_serve_ahead_error_does_not_direct_routine_migration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A newer schema never receives routine migration guidance it cannot satisfy."""
    database_state = "ahead"

    def fail_startup() -> None:
        raise SchemaCompatibilityError(
            "The GRC schema is ahead of this binary; deploy a compatible application.",
            recovery_action=SCHEMA_AHEAD_RECOVERY,
        )

    monkeypatch.setattr("cwl_grc.cli.create_app", fail_startup)

    assert cli_main(["serve"]) == 1
    next_action = json.loads(capsys.readouterr().out)["next_action"]
    assert database_state == "ahead"
    assert "Deploy an application build compatible with the newer schema" in next_action
    assert "migration owner" not in next_action
    assert "then check compatibility" not in next_action
