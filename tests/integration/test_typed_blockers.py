"""Typed Planner/Worker blockers, their routing, and what the evidence level may claim.

The dogfooding run found MARU treating a Planner that *refused* on governance grounds as a
successful cross-provider Arc: no blocker event, an ordinary approval gate, and a
CROSS_PROVIDER_REVIEW badge on an implementation that never happened. Everything here runs on
scripted agents; no model is ever called.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maru.cli.app import app
from maru.core.models import AgentRequest, AgentResult, ArcState, GateStatus
from maru.core.relay import RelayStopped, run_relay
from maru.storage.sqlite import SqliteStore

runner = CliRunner()

SLUG = "blockers"

_PLAN = {
    "goal": "Ship the change",
    "assumptions": [],
    "tasks": [{"id": "t1", "description": "Write docs/generated.md", "depends_on": []}],
    "acceptance_criteria": ["docs/generated.md exists"],
    "risks": [],
    "blocking_surface": ["AC1"],
    "blocker": None,
}
_PASS_PLAN_REVIEW = {"result": "pass", "findings": [], "recommendation": "continue"}
_IMPLEMENTATION = {
    "changed_files": ["docs/generated.md"],
    "notes": ["wrote the document"],
    "tests_expected": [],
    "unresolved_risks": [],
    "blocker": None,
}
_PASS_CODE_REVIEW = {"result": "pass", "blocking": [], "non_blocking": []}


def _blocker(classification: str, message: str, **extra) -> dict:
    return {
        "classification": classification,
        "message": message,
        "criterion": extra.get("criterion"),
        "authority": extra.get("authority"),
        "details": extra.get("details", []),
    }


def _blocked_plan(classification: str, message: str, **extra) -> dict:
    """A Planner that refused: no tasks, and the reason in the typed channel."""
    return _PLAN | {
        "goal": f"Escalate: {message}",
        "tasks": [],
        "acceptance_criteria": [],
        "blocking_surface": [],
        "blocker": _blocker(classification, message, **extra),
    }


def _blocked_implementation(classification: str, message: str, **extra) -> dict:
    return _IMPLEMENTATION | {
        "changed_files": [],
        "notes": [],
        "blocker": _blocker(classification, message, **extra),
    }


class Scripted:
    """One scripted backend. ``script[role]`` is a queue of structured artifacts for that role."""

    def __init__(
        self,
        backend: str,
        *,
        script: dict[str, list],
        calls: list[tuple[str, str]],
        writes: list[dict[str, str]] | None = None,
    ) -> None:
        self.backend = backend
        self.script = script
        self.calls = calls
        self.writes = writes if writes is not None else []

    def run(
        self, request: AgentRequest, *, cwd: Path, timeout_s: float | None = None
    ) -> AgentResult:
        role = request.role
        self.calls.append((role, self.backend))
        queue = self.script.get(role) or []
        response = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else None)
        assert response is not None, f"no scripted response for {role}"
        if role == "worker" and self.writes:
            files = self.writes.pop(0) if len(self.writes) > 1 else self.writes[0]
            for relative, content in files.items():
                target = cwd / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        run_dir = cwd / ".maru" / "fixture"
        run_dir.mkdir(parents=True, exist_ok=True)
        log = run_dir / "stdout.log"
        log.write_text("scripted", encoding="utf-8")
        now = datetime.now(UTC)
        return AgentResult(
            backend=self.backend,
            role=role,
            exit_code=0,
            stdout="",
            stderr="",
            structured_result=response,
            session_id=f"{self.backend}-session",
            started_at=now,
            finished_at=now,
            rendered_prompt_path=log,
            raw_log_path=log,
            stderr_path=log,
        )


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _project(tmp_path: Path, *, revisions: int = 2) -> Path:
    root = tmp_path / "project"
    (root / "tasks" / SLUG).mkdir(parents=True)
    (root / "docs").mkdir()
    (root / ".maru").mkdir()
    (root / ".maru" / "constitution.md").write_text(
        "8. docs/authority.txt requires explicit human authorization.", encoding="utf-8"
    )
    (root / ".gitignore").write_text(
        ".maru/maru.db\n.maru/maru.db-*\n.maru/runs/\n.maru/fixture/\n.maru/diff-index\n"
        "tasks/*/artifacts/\ntasks/*/logs/\ntasks/*/rendered/\n",
        encoding="utf-8",
    )
    (root / "docs" / "authority.txt").write_text("owner: human\n", encoding="utf-8")
    (root / "tasks" / SLUG / "request.md").write_text(
        "# What I want\n\nShip the change", encoding="utf-8"
    )
    (root / "maru.toml").write_text(
        '[agents.planner]\nbackend = "claude"\npermission = "read-only"\n'
        '[agents.challenger]\nbackend = "codex"\npermission = "read-only"\n'
        '[agents.worker]\nbackend = "claude"\npermission = "workspace-write"\n'
        '[agents.reviewer]\nbackend = "codex"\npermission = "read-only"\n'
        f"[limits]\nplan_revisions = {revisions}\nreview_fix_loops = 3\n"
        '[paths]\nstate_db = ".maru/maru.db"\ntasks = "tasks"\n',
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "relay@example.com")
    _git(root, "config", "user.name", "MARU test")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")
    return root


def _store(root: Path) -> SqliteStore:
    return SqliteStore(root / ".maru" / "maru.db")


def _events(root: Path, event_type: str) -> list[dict]:
    return [event.payload for event in _store(root).list_trace(SLUG) if event.type == event_type]


def _run(root: Path, script: dict, *, calls=None, writes=None, test_runner=None):
    calls = calls if calls is not None else []
    return run_relay(
        root,
        SLUG,
        adapter_factory=lambda backend: Scripted(
            backend, script=script, calls=calls, writes=writes
        ),
        test_runner=test_runner or (lambda _: (True, "checks ok")),
    )


# --- Planner typed blockers ----------------------------------------------------------------


def test_planner_authority_blocker_escalates_without_spending_a_revision(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []
    script = {
        "planner": [
            _blocked_plan(
                "HUMAN_AUTHORITY_REQUIRED",
                "Editing docs/authority.txt needs authority no agent here holds",
                authority=".maru/constitution.md rule 8",
                criterion="AC-01",
            )
        ]
    }

    with pytest.raises(RelayStopped):
        _run(root, script, calls=calls)

    # One Planner call: a governance refusal is not a plan defect, so no revision was spent,
    # and nothing downstream of the Planner ran at all.
    assert calls == [("planner", "claude")]

    raised = _events(root, "BLOCKER_RAISED")
    assert len(raised) == 1
    assert raised[0]["role"] == "planner"
    assert raised[0]["blocker"] == "HUMAN_AUTHORITY_REQUIRED"
    assert raised[0]["owner"] == "human"
    assert raised[0]["fixable_by_revision"] is False
    assert raised[0]["requires_decision"] is True
    assert raised[0]["authority"] == ".maru/constitution.md rule 8"
    assert raised[0]["criterion"] == "AC-01"

    # The escalation is a real, explicitly-marked Human Gate, not an ordinary approval.
    opened = _events(root, "GATE_OPENED")
    assert len(opened) == 1
    assert opened[0]["blocker"] == "HUMAN_AUTHORITY_REQUIRED"
    assert opened[0]["role"] == "planner"
    assert opened[0]["owner"] == "human"

    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED
    assert len(_store(root).list_open_gates(SLUG)) == 1


def test_a_refused_arc_is_never_labelled_cross_provider_review(tmp_path) -> None:
    root = _project(tmp_path)
    script = {
        "planner": [_blocked_plan("HUMAN_AUTHORITY_REQUIRED", "not mine to authorize")]
    }

    with pytest.raises(RelayStopped):
        _run(root, script)

    evidence = _events(root, "EVIDENCE_ASSESSED")
    assert [entry["evidence_level"] for entry in evidence] == ["BLOCKED_NO_IMPLEMENTATION"]
    assert evidence[0]["work_performed"] is False
    summary = (root / "tasks" / SLUG / "artifacts" / "human-summary.md").read_text("utf-8")
    assert "BLOCKED_NO_IMPLEMENTATION" in summary
    assert "No implementation was performed for this Arc." in summary
    assert "raised by Planner" in summary


def test_planner_capability_blocker_pauses_without_inventing_a_gate(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []
    script = {"planner": [_blocked_plan("CAPABILITY_MISSING", "no network on this machine")]}

    with pytest.raises(RelayStopped):
        _run(root, script, calls=calls)

    assert calls == [("planner", "claude")]
    raised = _events(root, "BLOCKER_RAISED")
    assert raised[0]["blocker"] == "CAPABILITY_MISSING"
    assert raised[0]["fixable_by_revision"] is False
    # Nothing here is a decision, so manufacturing a gate would only give a human a button
    # that cannot fix anything.
    assert _events(root, "GATE_OPENED") == []
    assert _store(root).list_open_gates(SLUG) == []
    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED


def test_a_plan_quality_blocker_is_the_one_kind_a_revision_may_answer(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []
    script = {
        "planner": [_blocked_plan("RULE_AMBIGUOUS", "two readings of the request"), _PLAN],
        "challenger": [_PASS_PLAN_REVIEW],
        "worker": [_IMPLEMENTATION],
        "reviewer": [_PASS_CODE_REVIEW],
    }

    _run(root, script, calls=calls, writes=[{"docs/generated.md": "generated\n"}])

    assert [role for role, _ in calls] == ["planner", "planner", "challenger", "worker", "reviewer"]
    raised = _events(root, "BLOCKER_RAISED")
    assert raised[0]["routed_to"] == "planner-revision"
    assert raised[0]["fixable_by_revision"] is True
    # The revision answered it, so the Arc reached an ordinary approval gate.
    assert _events(root, "EVIDENCE_ASSESSED")[-1]["evidence_level"] == "CROSS_PROVIDER_REVIEW"


def test_a_plan_quality_blocker_stops_once_the_revisions_run_out(tmp_path) -> None:
    root = _project(tmp_path, revisions=1)
    calls: list[tuple[str, str]] = []
    script = {"planner": [_blocked_plan("RULE_AMBIGUOUS", "still ambiguous")]}

    with pytest.raises(RelayStopped):
        _run(root, script, calls=calls)

    assert [role for role, _ in calls] == ["planner", "planner"]
    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED


# --- Worker typed blockers -----------------------------------------------------------------


def test_worker_capability_blocker_stops_the_fix_loop_immediately(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []
    gate_runs: list[int] = []

    def gate(_: Path) -> tuple[bool, str]:
        gate_runs.append(1)
        return True, "checks ok"

    script = {
        "planner": [_PLAN],
        "challenger": [_PASS_PLAN_REVIEW],
        "worker": [_blocked_implementation("CAPABILITY_MISSING", "no shell tool is available")],
        "reviewer": [_PASS_CODE_REVIEW],
    }

    with pytest.raises(RelayStopped):
        _run(root, script, calls=calls, test_runner=gate)

    # Exactly one Worker attempt, and the Reviewer never sees a non-existent implementation.
    assert [role for role, _ in calls] == ["planner", "challenger", "worker"]
    # A green gate on an empty tree must never stand in as evidence that the work succeeded.
    assert gate_runs == []
    assert _events(root, "TESTS_COMPLETED") == []

    raised = _events(root, "BLOCKER_RAISED")
    assert raised[0]["role"] == "worker"
    assert raised[0]["blocker"] == "CAPABILITY_MISSING"
    assert _events(root, "GATE_OPENED") == []
    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED


def test_worker_authority_blocker_opens_a_governance_gate_and_skips_review(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []
    script = {
        "planner": [_PLAN],
        "challenger": [_PASS_PLAN_REVIEW],
        "worker": [
            _blocked_implementation(
                "HUMAN_AUTHORITY_REQUIRED",
                "the plan needs docs/authority.txt edited",
                authority=".maru/constitution.md rule 8",
            )
        ],
        "reviewer": [_PASS_CODE_REVIEW],
    }

    with pytest.raises(RelayStopped):
        _run(root, script, calls=calls)

    assert [role for role, _ in calls] == ["planner", "challenger", "worker"]
    opened = _events(root, "GATE_OPENED")
    assert opened[0]["blocker"] == "HUMAN_AUTHORITY_REQUIRED"
    assert opened[0]["role"] == "worker"
    assert _events(root, "EVIDENCE_ASSESSED")[-1]["evidence_level"] == "BLOCKED_NO_IMPLEMENTATION"


# --- no-op versus blocked --------------------------------------------------------------------


def test_an_intentional_no_op_completes_and_says_so(tmp_path) -> None:
    root = _project(tmp_path)
    script = {
        "planner": [_PLAN],
        "challenger": [_PASS_PLAN_REVIEW],
        # Empty changed_files with no blocker: the Worker did the work and the right answer
        # was to change nothing. That is a completion, not a refusal.
        "worker": [_IMPLEMENTATION | {"changed_files": [], "notes": ["already correct"]}],
        "reviewer": [_PASS_CODE_REVIEW],
    }

    _run(root, script)

    assert _events(root, "BLOCKER_RAISED") == []
    evidence = _events(root, "EVIDENCE_ASSESSED")[-1]
    assert evidence["evidence_level"] == "INTENTIONAL_NOOP_COMPLETION"
    assert evidence["work_performed"] is False
    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.HUMAN_APPROVAL
    gates = _store(root).list_open_gates(SLUG)
    assert len(gates) == 1
    # It is a normal completion approval, so it must close the Arc the normal way.
    _, arc = _store(root).resolve_gate(gates[0].id, GateStatus.APPROVED)
    assert arc is not None and arc.state is ArcState.MERGED


def test_real_work_reviewed_by_a_second_provider_is_still_cross_provider(tmp_path) -> None:
    root = _project(tmp_path)

    _run(
        root,
        {
            "planner": [_PLAN],
            "challenger": [_PASS_PLAN_REVIEW],
            "worker": [_IMPLEMENTATION],
            "reviewer": [_PASS_CODE_REVIEW],
        },
        writes=[{"docs/generated.md": "generated\n"}],
    )

    evidence = _events(root, "EVIDENCE_ASSESSED")[-1]
    assert evidence["evidence_level"] == "CROSS_PROVIDER_REVIEW"
    assert evidence["work_performed"] is True
    assert evidence["changed_paths"] == ["docs/generated.md"]


# --- CLI surfaces ----------------------------------------------------------------------------


def test_inbox_and_status_name_a_governance_escalation_without_reading_event_json(
    tmp_path, monkeypatch
) -> None:
    root = _project(tmp_path)
    with pytest.raises(RelayStopped):
        _run(
            root,
            {
                "planner": [
                    _blocked_plan(
                        "HUMAN_AUTHORITY_REQUIRED",
                        "Planner refused the authority-file modification",
                        authority=".maru/constitution.md rule 8",
                    )
                ]
            },
        )
    monkeypatch.chdir(root)

    inbox = runner.invoke(app, ["inbox"])
    assert inbox.exit_code == 0
    assert "Governance decision required" in inbox.stdout
    assert "HUMAN_AUTHORITY_REQUIRED" in inbox.stdout
    assert "planner" in inbox.stdout
    assert "No implementation was performed" in inbox.stdout
    assert "Completion approval" not in inbox.stdout

    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0
    assert "HUMAN_AUTHORITY_REQUIRED" in status.stdout
    assert "BLOCKED_NO_IMPLEMENTATION" in status.stdout
    assert "Governance escalation" in status.stdout


def test_inbox_calls_an_ordinary_completion_gate_a_completion(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    _run(
        root,
        {
            "planner": [_PLAN],
            "challenger": [_PASS_PLAN_REVIEW],
            "worker": [_IMPLEMENTATION],
            "reviewer": [_PASS_CODE_REVIEW],
        },
        writes=[{"docs/generated.md": "generated\n"}],
    )
    monkeypatch.chdir(root)

    inbox = runner.invoke(app, ["inbox"])
    assert "Completion approval - evidence CROSS_PROVIDER_REVIEW" in inbox.stdout
    assert "Governance decision required" not in inbox.stdout


def test_rejecting_a_governance_escalation_leaves_no_active_arc(tmp_path, monkeypatch) -> None:
    """The zombie case: closing the gate must also close the Arc it belongs to."""
    root = _project(tmp_path)
    with pytest.raises(RelayStopped):
        _run(
            root,
            {"planner": [_blocked_plan("HUMAN_AUTHORITY_REQUIRED", "not mine to authorize")]},
        )
    store = _store(root)
    gates = store.list_open_gates(SLUG)
    assert len(gates) == 1
    arc = store.get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["reject", gates[0].id])

    assert result.exit_code == 0
    assert "REJECTED" in result.stdout
    arc = store.get_arc(SLUG)
    assert arc is not None
    assert arc.state is ArcState.REJECTED
    assert arc.current_agent is None
    assert arc.next_step == "Rejected by human"
    assert store.list_open_gates() == []
    assert store.list_active_arcs() == []
    assert "No active arc" in runner.invoke(app, ["status"]).stdout
    assert "Inbox empty" in runner.invoke(app, ["inbox"]).stdout


def test_approving_a_governance_escalation_says_the_work_still_has_to_happen(
    tmp_path, monkeypatch
) -> None:
    root = _project(tmp_path)
    with pytest.raises(RelayStopped):
        _run(
            root,
            {"planner": [_blocked_plan("HUMAN_AUTHORITY_REQUIRED", "not mine to authorize")]},
        )
    store = _store(root)
    gate_id = store.list_open_gates(SLUG)[0].id
    monkeypatch.chdir(root)

    result = runner.invoke(app, ["approve", gate_id])

    assert result.exit_code == 0
    assert "protected actions must be completed by the human" in result.stdout
    # The console may wrap the command across lines, so match the instruction, not the layout.
    assert "maru resume" in result.stdout
    # The Arc is still paused on purpose: authority was granted, the work was not done.
    arc = store.get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED
    assert store.list_open_gates() == []
    assert "Inbox empty" in runner.invoke(app, ["inbox"]).stdout
    assert SLUG in runner.invoke(app, ["status"]).stdout
    assert store.resume_arc(SLUG, source="human").state is ArcState.PLANNING
