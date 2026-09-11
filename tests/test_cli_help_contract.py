"""Keep parser help distinct from command failure and database/server execution."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import cwl_grc.cli as cli_module


@pytest.fixture(autouse=True)
def isolate_parser_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Require parser-only requests to terminate before any operational dispatch."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CWL_GRC_DATABASE_URL", raising=False)
    monkeypatch.delenv("CWL_GRC_SCHEMA_MODE", raising=False)

    def reject_operational_call(*arguments: object, **keywords: object) -> None:
        """Fail rather than substitute a successful store/server result."""
        pytest.fail("A parser-only request reached operational execution.")

    monkeypatch.setattr(cli_module, "_dispatch", reject_operational_call)
    monkeypatch.setattr(cli_module, "serve_http", reject_operational_call)
    monkeypatch.setattr(cli_module, "_open_session", reject_operational_call)


@pytest.mark.parametrize("command_prefix", [
    [], ["database"], ["database", "migrate"], ["database", "check"],
    ["policy"], ["policy", "author"], ["policy", "revise"], ["policy", "list"],
    ["gaps"], ["bind"],
])
def test_help_has_success_exit_without_runtime_configuration(
    command_prefix: list[str], capsys: pytest.CaptureFixture[str], tmp_path: Path,
) -> None:
    """Real argparse help does not become a failure or initialize a local store."""
    assert cli_module.main([*command_prefix, "--help"]) == 0
    captured_output = capsys.readouterr()
    assert "usage: cwl-grc" in captured_output.out
    assert captured_output.err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command_arguments", [
    ["unknown_command"], ["policy"], ["database"], ["database", "check"],
])
def test_argument_errors_keep_the_parser_failure_exit(
    command_arguments: list[str], capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid commands still return argparse's usage error, not startup JSON."""
    assert cli_module.main(command_arguments) == 2
    captured_output = capsys.readouterr()
    assert captured_output.out == ""
    assert "usage: cwl-grc" in captured_output.err
    assert "error:" in captured_output.err


@pytest.mark.parametrize("exit_code,expected_result", [(None, 2), (0, 0), (7, 7)])
def test_explicit_parser_exit_contract(
    exit_code: int | None, expected_result: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an absent exit code receives the fallback; explicit codes stay exact."""
    class ExplicitExitParser(argparse.ArgumentParser):
        """Exercise argparse's own exit method with each supported code case."""

        def parse_args(self, args=None, namespace=None):  # noqa: ANN001, ANN201
            """Terminate through the real parser exit rather than invoking a command."""
            self.exit(exit_code)

    parser_instance = ExplicitExitParser(prog="cwl-grc")
    monkeypatch.setattr(cli_module, "_parser", lambda: parser_instance)
    assert cli_module.main(["--help"]) == expected_result
