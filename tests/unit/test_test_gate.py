from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from maru.core.config import MaruConfig, load_config
from maru.core.testgate import DeterministicGateError, missing_executables, run_test_gate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _echo(text: str, *, exit_code: int = 0) -> list[str]:
    """A portable argv-only command: no shell, works identically on Windows and POSIX."""
    return [sys.executable, "-c", f"print({text!r}); raise SystemExit({exit_code})"]


def test_a_single_passing_command_passes_the_gate(tmp_path) -> None:
    passed, output = run_test_gate(
        tmp_path, [_echo("only check")], logs_dir=tmp_path / "logs", attempt=1
    )

    assert passed
    assert "only check" in output
    assert "PASS exit=0" in output


def test_commands_run_in_declaration_order(tmp_path) -> None:
    commands = [_echo("first"), _echo("second"), _echo("third")]

    _, output = run_test_gate(tmp_path, commands, logs_dir=tmp_path / "logs", attempt=1)

    assert output.index("first") < output.index("second") < output.index("third")


def test_a_failing_command_fails_the_gate_and_the_rest_still_run(tmp_path) -> None:
    """Documented rule: run-all, not fail-fast, so one fix loop sees every problem."""
    commands = [_echo("lint failed", exit_code=1), _echo("tests ran")]

    passed, output = run_test_gate(tmp_path, commands, logs_dir=tmp_path / "logs", attempt=1)

    assert not passed
    assert "FAIL exit=1" in output
    assert "tests ran" in output


def test_each_command_records_argv_exit_elapsed_and_an_artifact(tmp_path) -> None:
    logs = tmp_path / "logs"

    run_test_gate(tmp_path, [_echo("recorded")], logs_dir=logs, attempt=2)

    log = next(iter(logs.glob("tests-2-1-*.log")))
    body = log.read_text(encoding="utf-8")
    assert body.startswith("$ ")
    assert "# exit=0 elapsed=" in body
    assert "recorded" in body


def test_a_missing_executable_fails_the_gate_instead_of_raising(tmp_path) -> None:
    passed, output = run_test_gate(
        tmp_path, [["maru-no-such-tool", "--version"]], logs_dir=tmp_path / "logs", attempt=1
    )

    assert not passed
    assert "maru-no-such-tool" in output


def test_missing_executables_lists_unresolvable_commands() -> None:
    assert missing_executables([[sys.executable, "-c", "pass"]]) == []
    assert missing_executables([["maru-no-such-tool"]]) == ["maru-no-such-tool"]


def test_no_configured_commands_fails_closed(tmp_path) -> None:
    with pytest.raises(DeterministicGateError, match="No deterministic checks are configured"):
        run_test_gate(tmp_path, [], logs_dir=tmp_path / "logs", attempt=1)


def test_paths_containing_spaces_and_hangul_survive_argv(tmp_path) -> None:
    workdir = tmp_path / "한글 project dir"
    workdir.mkdir()
    script = workdir / "check script.py"
    script.write_text("print('space path ok')\n", encoding="utf-8")

    passed, output = run_test_gate(
        workdir, [[sys.executable, str(script)]], logs_dir=workdir / "logs", attempt=1
    )

    assert passed
    assert "space path ok" in output


def test_config_rejects_a_command_without_an_executable() -> None:
    with pytest.raises(ValueError, match="non-empty executable"):
        MaruConfig.model_validate({"agents": {}, "test_gate": {"commands": [[]]}})


def test_maru_keeps_its_own_ruff_and_pytest_gate_in_config_not_python() -> None:
    commands = load_config(REPO_ROOT).test_gate.commands

    assert ["uv", "run", "ruff", "check", "."] in commands
    assert ["uv", "run", "pytest"] in commands
    source = (REPO_ROOT / "src" / "maru" / "core" / "testgate.py").read_text(encoding="utf-8")
    assert "ruff" not in source and "pytest" not in source
    assert "MARU_UV_BIN" not in source


def test_maru_toml_test_gate_is_argv_arrays_only() -> None:
    raw = tomllib.loads((REPO_ROOT / "maru.toml").read_text(encoding="utf-8"))

    for command in raw["test_gate"]["commands"]:
        assert isinstance(command, list)
        assert all(isinstance(part, str) for part in command)
