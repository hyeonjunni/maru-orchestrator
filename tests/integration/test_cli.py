from __future__ import annotations

import unicodedata

import pytest
from rich.console import Console
from typer.testing import CliRunner

from maru.cli import app as cli_module
from maru.cli.app import app
from maru.core.models import Arc, ArcState, HumanGate
from maru.storage.sqlite import SqliteStore

runner = CliRunner()


def _pin_console(monkeypatch, width: int = 80) -> None:
    """Pin Rich's width so status output does not depend on the developer's terminal."""
    monkeypatch.setattr(cli_module, "console", Console(width=width, force_terminal=False))


def _store(root) -> SqliteStore:
    return SqliteStore(root / ".maru" / "maru.db")


def _create_arc(root, goal: str) -> str:
    """Seed an Arc directly. `maru run` now runs the whole relay, so it is not a fixture."""
    store = _store(root)
    store.initialize()
    arc = Arc(goal=goal)
    store.create_arc(arc)
    return arc.id


def _row_value(stdout: str, label: str) -> str:
    """Return the value cell of the status row carrying ``label``."""
    for line in stdout.splitlines():
        cells = line.lstrip(" │|┃")
        if cells.startswith(label):
            return cells.replace(label, "", 1).strip(" │|┃")
    raise AssertionError(f"row not found: {label}")


def _display_width(line: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in line)


def _hangul(text: str) -> str:
    """Goal text is the only Hangul in status output, so this rebuilds it across wrapped lines."""
    return "".join(char for char in text if "가" <= char <= "힣")


def test_init_creates_database_and_constitution_idempotently(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    first = runner.invoke(app, ["init"])
    second = runner.invoke(app, ["init"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (tmp_path / ".maru" / "maru.db").is_file()
    assert (tmp_path / ".maru" / "constitution.md").is_file()


def test_status_reports_no_active_arc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "No active arc" in result.stdout


def test_status_reports_no_active_arc_without_a_database(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "No active arc" in result.stdout


def test_status_reports_a_stored_arc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _pin_console(monkeypatch)
    assert runner.invoke(app, ["init"]).exit_code == 0
    arc_id = _create_arc(tmp_path, "로그인 기능 개선")

    status = runner.invoke(app, ["status"])

    assert status.exit_code == 0
    assert "로그인 기능 개선" in status.stdout
    assert "PLANNING" in status.stdout
    assert "Active Arc" in status.stdout
    assert _row_value(status.stdout, "Arc") == arc_id
    assert _row_value(status.stdout, "State") == "PLANNING"
    assert _row_value(status.stdout, "Current agent") == "-"
    assert _row_value(status.stdout, "Next step") == "-"
    assert _row_value(status.stdout, "Open gates") == "0"


def test_status_shows_stored_current_agent_and_next_step(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _pin_console(monkeypatch)
    assert runner.invoke(app, ["init"]).exit_code == 0
    _store(tmp_path).transition_arc(
        _create_arc(tmp_path, "릴레이 상태 요약"),
        ArcState.PLAN_REVIEW,
        source="core",
        current_agent="challenger",
        next_step="Challenger reviews the plan",
    )

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert _row_value(result.stdout, "State") == "PLAN_REVIEW"
    assert _row_value(result.stdout, "Current agent") == "challenger"
    assert _row_value(result.stdout, "Next step") == "Challenger reviews the plan"


def test_status_counts_open_gates_of_the_active_arc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _pin_console(monkeypatch)
    assert runner.invoke(app, ["init"]).exit_code == 0
    arc_id = _create_arc(tmp_path, "게이트 카운트 확인")
    _store(tmp_path).create_gate(HumanGate(arc_id=arc_id, reason="Approve relay result"))

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert _row_value(result.stdout, "Open gates") == "1"


def test_status_stays_readable_at_eighty_columns(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _pin_console(monkeypatch, width=80)
    assert runner.invoke(app, ["init"]).exit_code == 0
    goal = "로그인기능개선을위한회귀테스트정비와문서갱신" * 3
    arc_id = _create_arc(tmp_path, goal)

    result = runner.invoke(app, ["status"])

    lines = result.stdout.splitlines()
    assert result.exit_code == 0
    assert any(arc_id in line for line in lines)
    assert max(_display_width(line) for line in lines) <= 80
    assert _hangul(result.stdout) == goal


def test_doctor_reports_required_runtime_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    for field in ("OS", "Python", "Git", "Claude", "Codex", "UTF-8", "Config", "Database"):
        assert field in result.stdout


@pytest.mark.parametrize("command", [["init"], ["doctor"], ["run", "goal", "--slug", "demo"]])
@pytest.mark.parametrize(
    "config", ['[broken', '[agents.worker]\nbackend = "secret-value"\npermission = "read-only"']
)
def test_invalid_config_is_actionable_without_exposing_values(
    tmp_path, monkeypatch, command, config
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "maru.toml").write_text(config, encoding="utf-8")
    result = runner.invoke(app, command)
    assert result.exit_code == 2
    assert "maru.toml" in result.output
    assert "secret-value" not in result.output
    assert not (tmp_path / ".maru").exists()
    assert not (tmp_path / "tasks").exists()

