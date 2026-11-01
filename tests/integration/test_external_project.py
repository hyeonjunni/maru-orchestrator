"""Vertical slice: MARU driving a clean external repository that contains no MARU source.

The external repo has no `prompts/`, no `schemas/`, no MARU package and no copied harness.
Everything below runs with recorded agents; no Claude or Codex process is ever launched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from maru.cli import app as cli_module
from maru.cli.app import app
from maru.core import relay
from maru.core.models import AgentRequest, AgentResult, ArcState, GateStatus
from maru.storage.sqlite import SqliteStore

runner = CliRunner()

PROJECT_CHECK = [sys.executable, "-c", "print('project checks ok')"]


class RecordedAgents:
    """Replays fixed structured artifacts and, for the Worker, writes the planned files."""

    def __init__(
        self,
        backend: str,
        *,
        calls: list[tuple[str, str, str]],
        prompts: list[tuple[str, str]],
        worker_writes: dict[str, str],
        plan_task: str,
        sabotage: dict[str, Callable[[Path], None]] | None = None,
    ) -> None:
        self.backend = backend
        self.calls = calls
        self.prompts = prompts
        self.worker_writes = worker_writes
        self.plan_task = plan_task
        # Mutations applied after a named role finishes, to break the closure mid-relay.
        self.sabotage = sabotage or {}

    def run(
        self, request: AgentRequest, *, cwd: Path, timeout_s: float | None = None
    ) -> AgentResult:
        self.calls.append((request.role, self.backend, request.permission))
        self.prompts.append((request.role, request.prompt))
        if request.role in self.sabotage:
            self.sabotage[request.role](cwd)
        assert request.schema_path is not None and request.schema_path.is_file()
        assert json.loads(request.schema_path.read_text(encoding="utf-8"))
        if request.role == "worker":
            for relative, content in self.worker_writes.items():
                target = cwd / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        outputs = {
            "planner": {
                "goal": "Add the greeting",
                "assumptions": [],
                "tasks": [{"id": "t1", "description": self.plan_task, "depends_on": []}],
                "acceptance_criteria": ["greet() returns a greeting"],
                "risks": [],
            },
            "challenger": {"result": "pass", "findings": [], "recommendation": "continue"},
            "worker": {
                "changed_files": sorted(self.worker_writes),
                "notes": ["Implemented the approved task"],
                "tests_expected": ["tests/test_app.py"],
                "unresolved_risks": [],
            },
            "reviewer": {"result": "pass", "blocking": [], "non_blocking": []},
        }
        now = datetime.now(UTC)
        return AgentResult(
            backend=self.backend,
            role=request.role,
            exit_code=0,
            stdout="recorded",
            stderr="",
            structured_result=outputs[request.role],
            session_id=f"{self.backend}-session",
            started_at=now,
            finished_at=now,
            rendered_prompt_path=request.schema_path,
            raw_log_path=request.schema_path,
            stderr_path=request.schema_path,
        )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _external_repo(tmp_path: Path, *, commands: list[list[str]] | None = None) -> Path:
    """A real project: source, tests, a maru.toml, and nothing else MARU-shaped."""
    commands = [PROJECT_CHECK] if commands is None else commands
    gate = f"[test_gate]\ncommands = {json.dumps(commands)}\n" if commands else ""
    root = tmp_path / "sample 프로젝트"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "app.py").write_text("VERSION = 1\n", encoding="utf-8")
    (root / "tests" / "test_app.py").write_text("def test_app():\n    pass\n", encoding="utf-8")
    (root / "docs" / "brief.md").write_text("# Brief\n\nAdd a greeting.\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "maru.toml").write_text(
        f"""[agents.planner]
backend = "claude"
permission = "read-only"
[agents.challenger]
backend = "codex"
permission = "read-only"
[agents.worker]
backend = "claude"
permission = "workspace-write"
[agents.reviewer]
backend = "codex"
permission = "read-only"
{gate}""",
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "relay@example.com")
    _git(root, "config", "user.name", "MARU test")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "project baseline")
    return root


def _install_agents(monkeypatch, **kwargs) -> tuple[list, list]:
    calls: list[tuple[str, str, str]] = []
    prompts: list[tuple[str, str]] = []
    kwargs.setdefault("worker_writes", {"src/greeting.py": "def greet():\n    return 'hi'\n"})
    kwargs.setdefault("plan_task", "Add src/greeting.py with greet()")
    monkeypatch.setattr(
        relay,
        "default_adapter_factory",
        lambda backend: RecordedAgents(backend, calls=calls, prompts=prompts, **kwargs),
    )
    return calls, prompts


def _store(root: Path) -> SqliteStore:
    return SqliteStore(root / ".maru" / "maru.db")


def _init(root: Path, monkeypatch) -> None:
    monkeypatch.chdir(root)
    assert runner.invoke(app, ["init"]).exit_code == 0


def test_doctor_resolves_every_prompt_and_schema_without_a_copied_directory(
    tmp_path, monkeypatch
) -> None:
    root = _external_repo(tmp_path)
    _init(root, monkeypatch)
    # Wide console so the table reports full paths instead of folding them.
    monkeypatch.setattr(cli_module, "console", Console(width=400, force_terminal=False))

    doctor = runner.invoke(app, ["doctor"])

    assert doctor.exit_code == 0
    assert not (root / "prompts").exists()
    assert not (root / "schemas").exists()
    for role in ("planner", "challenger", "worker", "reviewer"):
        assert f"prompts/{role}.md" in doctor.stdout
    assert doctor.stdout.count("packaged (maru.assets/") == 8
    assert "error" not in doctor.stdout
    assert "project checks ok" in doctor.stdout
    assert "(ok)" in doctor.stdout  # the configured check resolves on this machine


def test_doctor_flags_an_unresolvable_check_command(tmp_path, monkeypatch) -> None:
    root = _external_repo(tmp_path, commands=[["maru-no-such-tool", "--check"]])
    _init(root, monkeypatch)
    monkeypatch.setattr(cli_module, "console", Console(width=400, force_terminal=False))

    doctor = runner.invoke(app, ["doctor"])

    assert "maru-no-such-tool --check (MISSING)" in doctor.stdout


def test_doctor_reports_a_project_override_and_a_broken_one(tmp_path, monkeypatch) -> None:
    root = _external_repo(tmp_path)
    _init(root, monkeypatch)
    (root / "prompts").mkdir()
    (root / "prompts" / "worker.md").write_text("Project worker.", encoding="utf-8")
    (root / "schemas").mkdir()
    (root / "schemas" / "review.schema.json").write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(cli_module, "console", Console(width=400, force_terminal=False))

    doctor = runner.invoke(app, ["doctor"])

    assert "project override" in doctor.stdout
    assert "error:" in doctor.stdout
    assert doctor.stdout.count("packaged (maru.assets/") == 6


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """External repo, initialized, with the request already written for slug `greeting`."""
    root = _external_repo(tmp_path)
    _init(root, monkeypatch)
    request = root.parent / "request.md"
    request.write_text("# What I want\n\nAdd a greeting helper.\n", encoding="utf-8")
    return root, request


def test_maru_bookkeeping_does_not_dirty_the_source_baseline(prepared, monkeypatch) -> None:
    root, request = prepared
    # git genuinely reports .maru as untracked; the relay must not read that as user work.
    assert ".maru/" in _git(root, "status", "--porcelain", "--untracked-files=normal")
    _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 0, result.stdout
    assert "clean git working tree" not in result.stdout


def test_a_genuine_untracked_source_file_still_blocks_the_worker(prepared, monkeypatch) -> None:
    root, request = prepared
    (root / "src" / "leftover.py").write_text("LEFTOVER = 1\n", encoding="utf-8")
    calls, _ = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "src/leftover.py" in result.stdout.replace("\n", "")
    assert "worker" not in [role for role, _, _ in calls]


def test_a_genuine_tracked_modification_still_blocks_the_worker(prepared, monkeypatch) -> None:
    root, request = prepared
    (root / "src" / "app.py").write_text("VERSION = 2\n", encoding="utf-8")
    calls, _ = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "src/app.py" in result.stdout.replace("\n", "")
    assert "worker" not in [role for role, _, _ in calls]
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "VERSION = 2\n"


def test_git_ignored_files_still_behave_as_git_says(prepared, monkeypatch) -> None:
    root, request = prepared
    (root / "src" / "__pycache__").mkdir()
    (root / "src" / "__pycache__" / "app.pyc").write_text("cached", encoding="utf-8")
    _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 0, result.stdout


def test_one_maru_run_drives_the_whole_relay_to_a_human_gate(prepared, monkeypatch) -> None:
    root, request = prepared
    calls, prompts = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 0, result.stdout
    assert [role for role, _, _ in calls] == ["planner", "challenger", "worker", "reviewer"]
    assert ("worker", "claude", "workspace-write") in calls
    assert "human-summary.md" in result.stdout.replace("\n", "")

    store = _store(root)
    arcs = store.list_active_arcs()
    assert [arc.id for arc in arcs] == ["greeting"]
    assert arcs[0].state is ArcState.HUMAN_APPROVAL
    events = store.list_trace("greeting")
    assert [event.type for event in events].count("ARC_CREATED") == 1
    assert all(event.arc_id == "greeting" for event in events)
    gates = store.list_open_gates()
    assert len(gates) == 1 and gates[0].arc_id == "greeting" and gates[0].status is GateStatus.OPEN


def test_the_configured_project_checks_run_instead_of_ruff_and_pytest(prepared, monkeypatch):
    root, request = prepared
    _, prompts = _install_agents(monkeypatch)

    runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    gate_log = (root / "tasks" / "greeting" / "logs" / "tests-1.log").read_text(encoding="utf-8")
    assert "project checks ok" in gate_log
    # Exactly the one configured command ran; MARU's own uv/ruff/pytest gate is not assumed.
    assert gate_log.count("PASS exit=0") == 1
    assert "ruff" not in gate_log and "uv run" not in gate_log
    reviewer_prompt = next(prompt for role, prompt in prompts if role == "reviewer")
    assert "project checks ok" in reviewer_prompt
    per_command = list((root / "tasks" / "greeting" / "logs").glob("tests-1-1-*.log"))
    assert per_command and "# exit=0 elapsed=" in per_command[0].read_text(encoding="utf-8")


def test_the_relay_diff_contains_only_the_worker_source_change(prepared, monkeypatch) -> None:
    root, request = prepared

    _install_agents(monkeypatch)
    runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    diff = (root / "tasks" / "greeting" / "artifacts" / "changes.diff").read_text(encoding="utf-8")
    assert "# Changed paths (1):" in diff
    assert "src/greeting.py" in diff
    assert ".maru/" not in diff
    assert "tasks/greeting" not in diff


def test_declared_inputs_are_snapshotted_and_visible_to_every_role(
    tmp_path, monkeypatch
) -> None:
    """Input-closure regression: a sibling checkout the Worker could never read."""
    sibling = tmp_path / "sibling-notes"
    sibling.mkdir()
    (sibling / "E00.md").write_text("Baseline experiment notes.\n", encoding="utf-8")
    root = _external_repo(tmp_path)
    _init(root, monkeypatch)
    request = root.parent / "request.md"
    request.write_text("# What I want\n\nUse the baseline notes.\n", encoding="utf-8")
    task_dir = root / "tasks" / "greeting"
    task_dir.mkdir(parents=True)
    (task_dir / "inputs.toml").write_text(
        f'[[inputs]]\nname = "e00"\npath = {json.dumps(str(sibling / "E00.md"))}\n',
        encoding="utf-8",
    )
    _, prompts = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 0, result.stdout
    snapshot = root / "tasks" / "greeting" / "inputs" / "e00.md"
    assert snapshot.read_text(encoding="utf-8") == "Baseline experiment notes.\n"
    for role in ("planner", "challenger", "worker", "reviewer"):
        prompt = next(text for name, text in prompts if name == role)
        assert "tasks/greeting/inputs/e00.md" in prompt
    manifest = json.loads(
        (root / "tasks" / "greeting" / "inputs" / "manifest.json").read_text(encoding="utf-8")
    )
    record = manifest["inputs"][0]
    assert record["source_path"].endswith("E00.md")
    assert len(record["sha256"]) == 64
    assert record["bytes"] > 0
    assert record["captured_at"]
    snapshotted = [
        event for event in _store(root).list_trace("greeting") if event.type == "INPUTS_SNAPSHOTTED"
    ]
    assert len(snapshotted) == 1


def _with_inputs(root: Path, sibling_file: Path, slug: str = "greeting") -> Path:
    task_dir = root / "tasks" / slug
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "inputs.toml").write_text(
        f'[[inputs]]\nname = "e00"\npath = {json.dumps(str(sibling_file))}\n', encoding="utf-8"
    )
    return task_dir


def _sibling_note(tmp_path: Path) -> Path:
    sibling = tmp_path / "sibling-notes"
    sibling.mkdir(exist_ok=True)
    note = sibling / "E00.md"
    note.write_text("Baseline experiment notes.\n", encoding="utf-8")
    return note


def test_a_missing_required_input_pauses_before_any_agent_runs(prepared, monkeypatch) -> None:
    root, request = prepared
    _with_inputs(root, root.parent / "never-written.md")
    calls, _ = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "BLOCKED_INPUT_CLOSURE" in result.stdout
    assert calls == []
    arc = _store(root).get_arc("greeting")
    assert arc is not None and arc.state is ArcState.PAUSED


def test_a_snapshot_deleted_mid_relay_pauses_before_the_worker(
    tmp_path, prepared, monkeypatch
) -> None:
    root, request = prepared
    _with_inputs(root, _sibling_note(tmp_path))
    calls, _ = _install_agents(
        monkeypatch,
        sabotage={"challenger": lambda cwd: (cwd / "tasks/greeting/inputs/e00.md").unlink()},
    )

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "BLOCKED_INPUT_CLOSURE" in result.stdout
    assert "snapshot missing" in result.stdout.replace("\n", "")
    roles = [role for role, _, _ in calls]
    assert roles == ["planner", "challenger"]
    assert "worker" not in roles and "reviewer" not in roles


def test_a_tampered_snapshot_fails_with_a_sha_mismatch(tmp_path, prepared, monkeypatch) -> None:
    root, request = prepared
    _with_inputs(root, _sibling_note(tmp_path))
    calls, _ = _install_agents(
        monkeypatch,
        sabotage={
            "challenger": lambda cwd: (cwd / "tasks/greeting/inputs/e00.md").write_text(
                "tampered", encoding="utf-8"
            )
        },
    )

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "SHA-256 changed since capture" in result.stdout.replace("\n", "")
    assert "worker" not in [role for role, _, _ in calls]


def test_the_closure_failure_is_recorded_as_a_preflight_event(
    tmp_path, prepared, monkeypatch
) -> None:
    root, request = prepared
    _with_inputs(root, _sibling_note(tmp_path))
    _install_agents(
        monkeypatch,
        sabotage={"challenger": lambda cwd: (cwd / "tasks/greeting/inputs/e00.md").unlink()},
    )

    runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    events = _store(root).list_trace("greeting")
    preflight = [event for event in events if event.type == "PREFLIGHT_FAILED"]
    assert len(preflight) == 1
    assert preflight[0].payload["reason"] == "BLOCKED_INPUT_CLOSURE"
    assert preflight[0].payload["problems"]
    assert "TESTS_COMPLETED" not in {event.type for event in events}
    assert "GATE_OPENED" not in {event.type for event in events}


def test_a_project_without_configured_checks_fails_closed_before_the_worker(
    tmp_path, monkeypatch
) -> None:
    root = _external_repo(tmp_path, commands=[])
    _init(root, monkeypatch)
    request = root.parent / "request.md"
    request.write_text("# What I want\n\nAdd a greeting helper.\n", encoding="utf-8")
    calls, _ = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "BLOCKED_CAPABILITY" in result.stdout
    assert "no deterministic checks configured" in result.stdout.replace("\n", "")
    assert "worker" not in [role for role, _, _ in calls]


def test_an_unresolvable_check_executable_pauses_before_the_worker(tmp_path, monkeypatch) -> None:
    root = _external_repo(tmp_path, commands=[["maru-no-such-tool", "--check"]])
    _init(root, monkeypatch)
    request = root.parent / "request.md"
    request.write_text("# What I want\n\nAdd a greeting helper.\n", encoding="utf-8")
    calls, _ = _install_agents(monkeypatch)

    result = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert result.exit_code == 2
    assert "maru-no-such-tool" in result.stdout.replace("\n", "")
    assert "worker" not in [role for role, _, _ in calls]


def test_a_paused_relay_resumes_and_never_creates_a_second_arc(
    tmp_path, prepared, monkeypatch
) -> None:
    root, request = prepared
    _with_inputs(root, root.parent / "never-written.md")
    _install_agents(monkeypatch)
    assert runner.invoke(
        app, ["run", "--prompt-file", str(request), "--slug", "greeting"]
    ).exit_code == 2

    assert runner.invoke(app, ["resume", "greeting"]).exit_code == 0
    (root / "tasks" / "greeting" / "inputs.toml").unlink()
    second = runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    assert second.exit_code == 0, second.stdout
    store = _store(root)
    assert [arc.id for arc in store.list_active_arcs()] == ["greeting"]
    types = [event.type for event in store.list_trace("greeting")]
    assert types.count("ARC_CREATED") == 1
    assert types.count("ARC_RESTORED") == 1
    assert "GATE_OPENED" in types


def test_status_and_trace_read_back_the_same_slug(prepared, monkeypatch) -> None:
    root, request = prepared
    _install_agents(monkeypatch)
    runner.invoke(app, ["run", "--prompt-file", str(request), "--slug", "greeting"])

    status = runner.invoke(app, ["status"])
    trace = runner.invoke(app, ["trace", "greeting"])
    inbox = runner.invoke(app, ["inbox"])

    assert "greeting" in status.stdout
    assert "HUMAN_APPROVAL" in status.stdout
    assert "ARC_CREATED" in trace.stdout
    assert "GATE_OPENED" in trace.stdout
    assert "greeting" in inbox.stdout
