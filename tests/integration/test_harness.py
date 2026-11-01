from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maru.cli.app import app
from maru.core.models import AgentRequest, AgentResult, ArcState, GateStatus
from maru.storage.sqlite import SqliteStore
from scripts.proto_harness import RelayStopped, run_relay


class ScriptedAdapter:
    def __init__(
        self,
        backend: str,
        calls: list[tuple[str, str, str]],
        challenger_passes: bool,
        *,
        contradictory: bool = False,
        prompts: list[tuple[str, str]] | None = None,
        worker_writes: dict[str, str] | list[dict[str, str]] | None = None,
        plan_tasks: list[dict[str, object]] | None = None,
    ) -> None:
        self.backend = backend
        self.calls = calls
        self.challenger_passes = challenger_passes
        self.contradictory = contradictory
        self.prompts = prompts
        # A list writes a different set per Worker attempt, so a relay can be driven
        # through several iterations with distinct edits.
        self.worker_writes = worker_writes or {}
        self.plan_tasks = plan_tasks or [
            {"id": "task-1", "description": "Implement status", "depends_on": []}
        ]

    def run(
        self, request: AgentRequest, *, cwd: Path, timeout_s: float | None = None
    ) -> AgentResult:
        self.calls.append((request.role, self.backend, request.permission))
        if self.prompts is not None:
            self.prompts.append((request.role, request.prompt))
        if request.role == "worker":
            writes = self.worker_writes
            if isinstance(writes, list):
                # The relay builds a fresh adapter per stage, so the shared list is the counter.
                writes = writes.pop(0) if len(writes) > 1 else (writes[0] if writes else {})
            for relative, content in writes.items():
                target = cwd / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        outputs = {
            "planner": {
                "goal": "Finish status",
                "assumptions": [],
                "tasks": self.plan_tasks,
                "acceptance_criteria": ["Empty state does not crash"],
                "risks": [],
            },
            "challenger": {
                "result": "pass" if self.challenger_passes else "fail",
                "findings": []
                if self.challenger_passes and not self.contradictory
                else [{"severity": "blocking", "evidence": "missing", "message": "revise"}],
                "recommendation": "continue" if self.challenger_passes else "revise",
            },
            "worker": {
                "changed_files": ["src/maru/cli/app.py"],
                "notes": ["Filled in the status table"],
                "tests_expected": ["tests/integration/test_cli.py"],
                "unresolved_risks": [],
            },
            "reviewer": {"result": "pass", "blocking": [], "non_blocking": []},
        }
        run_dir = cwd / ".maru" / "fixture"
        run_dir.mkdir(parents=True, exist_ok=True)
        prompt = run_dir / "prompt.md"
        stdout = run_dir / "stdout.log"
        stderr = run_dir / "stderr.log"
        prompt.write_text(request.prompt, encoding="utf-8")
        stdout.write_text("fixture", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        now = datetime.now(UTC)
        return AgentResult(
            backend=self.backend,
            role=request.role,
            exit_code=0,
            stdout="fixture",
            stderr="",
            structured_result=outputs[request.role],
            session_id=f"{self.backend}-session",
            started_at=now,
            finished_at=now,
            rendered_prompt_path=prompt,
            raw_log_path=stdout,
            stderr_path=stderr,
        )


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _project(tmp_path: Path, *, revisions: int = 2, worker_backend: str = "claude") -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "tasks" / "first-relay").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / ".maru").mkdir()
    (tmp_path / ".maru" / "constitution.md").write_text("protected", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(
        ".maru/maru.db\n.maru/maru.db-*\n.maru/runs/\n.maru/fixture/\n"
        "tasks/*/artifacts/\ntasks/*/logs/\ntasks/*/rendered/\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "tasks" / "first-relay" / "request.md").write_text(
        "# What I want\n\nFinish status", encoding="utf-8"
    )
    schema_names = {
        "planner": "plan.schema.json",
        "challenger": "plan_review.schema.json",
        "worker": "implementation.schema.json",
        "reviewer": "review.schema.json",
    }
    for role in ("planner", "challenger", "worker", "reviewer"):
        (tmp_path / "prompts" / f"{role}.md").write_text(f"You are {role}.", encoding="utf-8")
        (tmp_path / "schemas" / schema_names[role]).write_text("{}", encoding="utf-8")
    (tmp_path / "maru.toml").write_text(
        f"""[agents.planner]
backend = "codex"
permission = "read-only"
[agents.challenger]
backend = "claude"
permission = "read-only"
[agents.worker]
backend = "{worker_backend}"
permission = "workspace-write"
[agents.reviewer]
backend = "claude"
permission = "read-only"
[limits]
plan_revisions = {revisions}
review_fix_loops = 3
[paths]
state_db = ".maru/maru.db"
tasks = "tasks"
""",
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "relay@example.com")
    _git(tmp_path, "config", "user.name", "MARU test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "fixture")
    return tmp_path


def _store(root: Path) -> SqliteStore:
    return SqliteStore(root / ".maru" / "maru.db")


def test_relay_uses_configured_backends_and_writes_human_summary(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str, str]] = []

    summary = run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, calls, True),
        test_runner=lambda _: (True, "ruff: pass\npytest: pass"),
    )

    assert calls == [
        ("planner", "codex", "read-only"),
        ("challenger", "claude", "read-only"),
        ("worker", "claude", "workspace-write"),
        ("reviewer", "claude", "read-only"),
    ]
    assert "Ready for human review" in summary.read_text(encoding="utf-8")
    artifacts = root / "tasks" / "first-relay" / "artifacts"
    assert {path.name for path in artifacts.iterdir()} == {
        "plan.json",
        "plan-review.json",
        "implementation.json",
        "code-review.json",
        "changes.diff",
        "human-summary.md",
        "history",
    }


def test_relay_persists_arc_states_events_and_a_human_gate(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str, str]] = []

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, calls, True),
        test_runner=lambda _: (True, "pass"),
    )

    store = _store(root)
    arc = store.get_arc("first-relay")
    assert arc is not None
    assert arc.goal == "Finish status"
    assert arc.state is ArcState.HUMAN_APPROVAL
    assert arc.current_agent == "human"
    assert arc.next_step == "Approve or reject the open gate"
    assert [a.id for a in store.list_active_arcs()] == ["first-relay"]

    events = store.list_trace("first-relay")
    assert [event.payload["to"] for event in events if event.type == "STATE_TRANSITIONED"] == [
        "PLAN_REVIEW",
        "IMPLEMENTING",
        "TESTING",
        "CODE_REVIEW",
        "HUMAN_APPROVAL",
    ]
    assert [event.source for event in events if event.type == "AGENT_COMPLETED"] == [
        "planner",
        "challenger",
        "worker",
        "reviewer",
    ]
    assert {"ARC_CREATED", "DIFF_CAPTURED", "TESTS_COMPLETED", "GATE_OPENED"} <= {
        event.type for event in events
    }

    plan_event = next(event for event in events if event.source == "planner")
    # The latest pointer and the immutable copy of the same invocation are both recorded.
    assert [str(ref.path) for ref in plan_event.artifact_refs] == [
        str(Path("tasks/first-relay/artifacts/plan.json")),
        str(Path("tasks/first-relay/artifacts/history/planner/001.json")),
    ]

    gates = store.list_open_gates()
    assert len(gates) == 1
    assert gates[0].arc_id == "first-relay"
    assert gates[0].status is GateStatus.OPEN


def test_reviewer_receives_the_captured_repository_diff(tmp_path) -> None:
    root = _project(tmp_path)
    prompts: list[tuple[str, str]] = []

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(
            backend,
            [],
            True,
            prompts=prompts,
            worker_writes={"src/app.py": "print('worker was here')\n"},
        ),
        test_runner=lambda _: (True, "pass"),
    )

    diff = (root / "tasks" / "first-relay" / "artifacts" / "changes.diff").read_text(
        encoding="utf-8"
    )
    assert "src/app.py" in diff
    reviewer_prompt = next(prompt for role, prompt in prompts if role == "reviewer")
    assert "src/app.py" in reviewer_prompt
    assert "MARU executed the deterministic tests; the Worker did not." in reviewer_prompt


def test_relay_stops_when_worker_edits_the_tests_that_grade_it(tmp_path) -> None:
    root = _project(tmp_path)

    with pytest.raises(RelayStopped, match="unapproved-grading-change"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(
                backend,
                [],
                True,
                worker_writes={"tests/test_demo.py": "def test_demo():\n    assert True\n"},
            ),
            test_runner=lambda _: (True, "pass"),
        )

    summary = root / "tasks" / "first-relay" / "artifacts" / "human-summary.md"
    assert "tests/test_demo.py" in summary.read_text(encoding="utf-8")


def test_relay_allows_test_changes_the_approved_plan_asks_for(tmp_path) -> None:
    root = _project(tmp_path)

    summary = run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(
            backend,
            [],
            True,
            worker_writes={"tests/test_demo.py": "def test_demo():\n    assert True\n"},
            plan_tasks=[
                {
                    "id": "task-1",
                    "description": "Extend tests/test_demo.py to cover the empty state",
                    "depends_on": [],
                }
            ],
        ),
        test_runner=lambda _: (True, "pass"),
    )

    assert "Ready for human review" in summary.read_text(encoding="utf-8")


def test_relay_stops_when_worker_touches_a_protected_file(tmp_path) -> None:
    root = _project(tmp_path)

    with pytest.raises(RelayStopped, match="constitution-update"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(
                backend, [], True, worker_writes={".maru/constitution.md": "tampered"}
            ),
            test_runner=lambda _: (True, "pass"),
        )


def test_stopped_relay_leaves_a_resumable_arc_and_its_history(tmp_path) -> None:
    root = _project(tmp_path, revisions=1)

    with pytest.raises(RelayStopped, match="Plan revision limit"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(backend, [], False),
            test_runner=lambda _: (True, "unused"),
        )

    store = _store(root)
    arc = store.get_arc("first-relay")
    assert arc is not None
    assert arc.state is ArcState.PAUSED
    assert arc.next_step == "Plan revision limit exceeded"
    assert [a.id for a in store.list_active_arcs()] == ["first-relay"]
    events = store.list_trace("first-relay")
    assert "RELAY_STOPPED" in {event.type for event in events}
    assert store.resume_arc("first-relay", source="human").state is ArcState.PLAN_REVIEW


def test_second_relay_run_restores_the_existing_arc(tmp_path) -> None:
    root = _project(tmp_path, revisions=1)
    factory = lambda backend: ScriptedAdapter(backend, [], False)  # noqa: E731

    for _ in range(2):
        with pytest.raises(RelayStopped, match="Plan revision limit"):
            run_relay(
                root, "first-relay", adapter_factory=factory, test_runner=lambda _: (True, "")
            )

    store = _store(root)
    assert [arc.id for arc in store.list_active_arcs()] == ["first-relay"]
    assert "ARC_RESTORED" in {event.type for event in store.list_trace("first-relay")}


def test_relay_stops_after_configured_plan_revision_limit(tmp_path) -> None:
    root = _project(tmp_path, revisions=1)
    calls: list[tuple[str, str, str]] = []
    prompts: list[tuple[str, str]] = []

    with pytest.raises(RelayStopped, match="Plan revision limit"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(
                backend, calls, False, prompts=prompts
            ),
            test_runner=lambda _: (True, "unused"),
        )

    assert [role for role, _, _ in calls] == ["planner", "challenger", "planner", "challenger"]
    second_plan_prompt = [prompt for role, prompt in prompts if role == "planner"][1]
    assert '"goal": "Finish status"' in second_plan_prompt
    assert '"result": "fail"' in second_plan_prompt
    summary = root / "tasks" / "first-relay" / "artifacts" / "human-summary.md"
    assert "Human intervention required" in summary.read_text(encoding="utf-8")


def test_relay_rejects_contradictory_passing_review(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str, str]] = []

    with pytest.raises(RelayStopped, match="Invalid challenger artifact"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(
                backend, calls, True, contradictory=True
            ),
            test_runner=lambda _: (True, "unused"),
        )

    summary = root / "tasks" / "first-relay" / "artifacts" / "human-summary.md"
    assert "Human intervention required" in summary.read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", ["../outside", "nested/task", "C:\\outside"])
def test_relay_rejects_task_paths_outside_the_tasks_root(tmp_path, slug) -> None:
    root = _project(tmp_path)

    with pytest.raises(RelayStopped, match="Invalid task slug"):
        run_relay(root, slug)


def test_relay_turns_adapter_launch_failure_into_human_stop(tmp_path) -> None:
    root = _project(tmp_path)

    with pytest.raises(RelayStopped, match="planner could not run"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda _: (_ for _ in ()).throw(OSError("missing CLI")),
        )

    summary = root / "tasks" / "first-relay" / "artifacts" / "human-summary.md"
    assert "Human intervention required" in summary.read_text(encoding="utf-8")


def test_relay_runs_a_codex_worker_when_maru_toml_says_so(tmp_path) -> None:
    root = _project(tmp_path, worker_backend="codex")
    calls: list[tuple[str, str, str]] = []

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, calls, True),
        test_runner=lambda _: (True, "pass"),
    )

    assert ("worker", "codex", "workspace-write") in calls


def test_cli_reads_back_the_relay_from_the_state_store(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, [], True),
        test_runner=lambda _: (True, "pass"),
    )
    monkeypatch.chdir(root)
    runner = CliRunner()

    status = runner.invoke(app, ["status"])
    inbox = runner.invoke(app, ["inbox"])
    trace = runner.invoke(app, ["trace", "first-relay"])

    assert "HUMAN_APPROVAL" in status.stdout
    assert "human" in status.stdout
    assert "Approve or reject" in status.stdout
    assert "first-relay" in inbox.stdout
    assert "Approve relay result" in inbox.stdout
    assert "AGENT_COMPLETED" in trace.stdout
    assert "plan.json" in trace.stdout
    assert "GATE_OPENED" in trace.stdout


def test_failed_test_gate_loops_back_through_implementing(tmp_path) -> None:
    root = _project(tmp_path)
    attempts: list[int] = []

    def failing_then_passing(_: Path) -> tuple[bool, str]:
        attempts.append(len(attempts))
        return len(attempts) > 1, f"attempt {len(attempts)}"

    summary = run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, [], True),
        test_runner=failing_then_passing,
    )

    assert len(attempts) == 2
    assert "Ready for human review" in summary.read_text(encoding="utf-8")
    transitions = [
        event.payload["to"]
        for event in _store(root).list_trace("first-relay")
        if event.type == "STATE_TRANSITIONED"
    ]
    assert transitions == [
        "PLAN_REVIEW",
        "IMPLEMENTING",
        "TESTING",
        "CODE_REVIEW",
        "IMPLEMENTING",
        "TESTING",
        "CODE_REVIEW",
        "HUMAN_APPROVAL",
    ]
    events = _store(root).list_trace("first-relay")
    assert [e.payload["passed"] for e in events if e.type == "TESTS_COMPLETED"] == [False, True]


def _artifact(root: Path, name: str) -> str:
    return (root / "tasks" / "first-relay" / "artifacts" / name).read_text(encoding="utf-8")


def _reviewer_prompts(prompts: list[tuple[str, str]]) -> list[str]:
    return [prompt for role, prompt in prompts if role == "reviewer"]


def _failing_then_passing():
    """Test gate that fails once, which is what drives a second Worker iteration."""
    attempts: list[int] = []

    def runner(_: Path) -> tuple[bool, str]:
        attempts.append(len(attempts))
        return len(attempts) > 1, f"attempt {len(attempts)}"

    return runner


def test_relay_pauses_before_the_worker_when_a_tracked_file_is_dirty(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert 1\n", encoding="utf-8"
    )
    calls: list[tuple[str, str, str]] = []

    with pytest.raises(RelayStopped, match="clean git working tree"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(backend, calls, True),
            test_runner=lambda _: (True, "pass"),
        )

    assert "worker" not in [role for role, _, _ in calls]
    assert "tests/test_demo.py" in _artifact(root, "human-summary.md")
    # Fail closed: the human's uncommitted work is still exactly where they left it.
    assert (root / "tests" / "test_demo.py").read_text(encoding="utf-8") == (
        "def test_demo():\n    assert 1\n"
    )
    arc = _store(root).get_arc("first-relay")
    assert arc is not None and arc.state is ArcState.PAUSED


def test_relay_pauses_before_the_worker_when_an_untracked_source_file_is_dirty(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "leftover.py").write_text("LEFTOVER = 1\n", encoding="utf-8")
    calls: list[tuple[str, str, str]] = []

    with pytest.raises(RelayStopped, match="clean git working tree"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda backend: ScriptedAdapter(backend, calls, True),
            test_runner=lambda _: (True, "pass"),
        )

    assert "worker" not in [role for role, _, _ in calls]
    assert "src/leftover.py" in _artifact(root, "human-summary.md")
    assert (root / "src" / "leftover.py").is_file()


def test_ignored_runtime_files_and_task_directories_leave_the_baseline_clean(tmp_path) -> None:
    root = _project(tmp_path)
    (root / ".maru" / "runs" / "run-1").mkdir(parents=True)
    (root / ".maru" / "runs" / "run-1" / "stdout.log").write_text("noise", encoding="utf-8")
    (root / "tasks" / "first-relay" / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "first-relay" / "artifacts" / "stale.diff").write_text(
        "old", encoding="utf-8"
    )
    (root / "tasks" / "other-task").mkdir()
    (root / "tasks" / "other-task" / "request.md").write_text("later", encoding="utf-8")

    summary = run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(backend, [], True),
        test_runner=lambda _: (True, "pass"),
    )

    assert "Ready for human review" in summary.read_text(encoding="utf-8")
    diff = _artifact(root, "changes.diff")
    assert "# Changed paths (0):" in diff
    assert "tasks/other-task/request.md" not in diff


def test_changes_diff_shows_tracked_edits_and_new_file_contents(tmp_path) -> None:
    root = _project(tmp_path)

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(
            backend,
            [],
            True,
            worker_writes={
                "tests/test_demo.py": "def test_demo():\n    assert True\n",
                "src/new_module.py": "VALUE = 1\n",
            },
            plan_tasks=[
                {
                    "id": "task-1",
                    "description": "Add src/new_module.py and extend tests/test_demo.py",
                    "depends_on": [],
                }
            ],
        ),
        test_runner=lambda _: (True, "pass"),
    )

    diff = _artifact(root, "changes.diff")
    assert diff.startswith("# Relay changes since baseline")
    assert "# Changed paths (2):" in diff
    assert "+    assert True" in diff
    # `git diff` never shows an untracked file, so the Reviewer needs its content spelled out.
    assert "+++ b/src/new_module.py" in diff
    assert "+VALUE = 1" in diff


def test_changes_diff_never_attributes_the_cumulative_diff_to_the_latest_worker(tmp_path) -> None:
    root = _project(tmp_path)
    prompts: list[tuple[str, str]] = []
    # One dict per Worker attempt, built once so every adapter instance shares it.
    writes = [{"src/first.py": "FIRST = 1\n"}, {}]

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(
            backend,
            [],
            True,
            prompts=prompts,
            worker_writes=writes,
        ),
        test_runner=_failing_then_passing(),
    )

    diff = _artifact(root, "changes.diff")
    reviewed = _reviewer_prompts(prompts)
    assert len(reviewed) == 2
    # The second Worker changed nothing, yet the relay evidence stays complete and truthful.
    for text in (diff, *reviewed):
        assert "Worker-changed paths" not in text
        assert "# Changed paths (1):" in text
        assert "src/first.py" in text
    assert "+FIRST = 1" in diff


def test_later_worker_iterations_accumulate_into_one_relay_diff(tmp_path) -> None:
    root = _project(tmp_path)
    prompts: list[tuple[str, str]] = []
    writes = [{"src/first.py": "FIRST = 1\n"}, {"src/second.py": "SECOND = 2\n"}]

    run_relay(
        root,
        "first-relay",
        adapter_factory=lambda backend: ScriptedAdapter(
            backend,
            [],
            True,
            prompts=prompts,
            worker_writes=writes,
        ),
        test_runner=_failing_then_passing(),
    )

    diff = _artifact(root, "changes.diff")
    assert "# Changed paths (2):" in diff
    assert "+FIRST = 1" in diff
    assert "+SECOND = 2" in diff
    assert "src/second.py" in _reviewer_prompts(prompts)[1]

    captured = [e for e in _store(root).list_trace("first-relay") if e.type == "DIFF_CAPTURED"]
    # The guard still grades one Worker invocation; only the review evidence is cumulative.
    assert [event.payload["worker_changed_paths"] for event in captured] == [
        ["src/first.py"],
        ["src/second.py"],
    ]
    assert captured[1].payload["relay_changed_paths"] == ["src/first.py", "src/second.py"]
    assert captured[0].payload["baseline_commit"] == captured[1].payload["baseline_commit"]
