"""Regression coverage for operator-facing HTTP serve startup failures."""

from __future__ import annotations

import json

from cwl_grc.cli import main as cli_main
from cwl_grc.database import SchemaCompatibilityError


def test_serve_reports_schema_failure_with_next_action(monkeypatch, capsys) -> None:
    """Return actionable JSON instead of a traceback when serving an incompatible schema."""

    def fail_startup():  # noqa: ANN202
        raise SchemaCompatibilityError("The stored GRC schema is incompatible with this build.")

    monkeypatch.setattr("cwl_grc.cli.create_app", fail_startup)

    assert cli_main(["serve"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "error": "The stored GRC schema is incompatible with this build.",
        "next_action": "Run the explicit database migration owner, then check compatibility.",
    }
