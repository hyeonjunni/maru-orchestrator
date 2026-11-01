"""MARU v0.2: immutable iteration artifacts, terminal gates, typed blockers, fallback, and
incremental review context. Everything here runs on scripted agents; no model is ever called.
"""

from __future__ import annotations

import json
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

SLUG = "v02"

_PLAN = {
    "goal": "Ship the change",
    "assumptions": [],
    "tasks": [{"id": "t1", "description": "Write docs/generated.md", "depends_on": []}],
    "acceptance_criteria": ["docs/generated.md exists"],
    "risks": [],
    "blocking_surface": ["AC1-generated-doc"],
}
_PASS_REVIEW = {"result": "pass", "findings": [], "recommendation": "continue"}
_IMPLEMENTATION = {
    "changed_files": ["docs/generated.md"],
    "notes": ["wrote the document"],
    "tests_expected": [],
    "unresolved_risks": [],
}
_PASS_CODE_REVIEW = {"result": "pass", "blocking": [], "non_blocking": []}


class Scripted:
    """One scripted backend. `script[role]` is a queue of responses for that role.

    A response is either a structured artifact dict, or a `Failure` describing a process that
    exits non-zero - which is how provider quota exhaustion is simulated.
    """

    def __init__(
        self,
        backend: str,
        *,
        script: dict[str, list],
        calls: list[tuple[str, str]],
        prompts: list[tuple[str, str]],
        writes: dict[str, list[dict[str, str]]] | None = None,
    ) -> None:
        self.backend = backend
        self.script = script
        self.calls = calls
        self.prompts = prompts
        self.writes = writes or {}

    def run(
        self, request: AgentRequest, *, cwd: Path, timeout_s: float | None = None
    ) -> AgentResult:
        role = request.role
        self.calls.append((role, self.backend))
        self.prompts.append((role, request.prompt))
        queue = self.script.get(f"{role}@{self.backend}") or self.script.get(role) or []
        response = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else None)
        assert response is not None, f"no scripted response for {role}@{self.backend}"
        if role == "worker":
            pending = self.writes.get("worker", [])
            files = pending.pop(0) if len(pending) > 1 else (pending[0] if pending else {})
            for relative, content in files.items():
                target = cwd / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        run_dir = cwd / ".maru" / "fixture"
        run_dir.mkdir(parents=True, exist_ok=True)
        log = run_dir / "stdout.log"
        log.write_text("scripted", encoding="utf-8")
        now = datetime.now(UTC)
        failed = isinstance(response, Failure)
        return AgentResult(
            backend=self.backend,
            role=role,
            exit_code=response.exit_code if failed else 0,
            stdout="",
            stderr=response.stderr if failed else "",
            structured_result=None if failed else response,
            session_id=f"{self.backend}-session",
            started_at=now,
            finished_at=now,
            rendered_prompt_path=log,
            raw_log_path=log,
            stderr_path=log,
        )


class Failure:
    def __init__(self, stderr: str, exit_code: int = 1) -> None:
        self.stderr = stderr
        self.exit_code = exit_code


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _project(tmp_path: Path, *, extra: str = "", agents: str | None = None) -> Path:
    root = tmp_path / "project"
    (root / "tasks" / SLUG).mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "tests").mkdir()
    (root / ".maru").mkdir()
    (root / ".maru" / "constitution.md").write_text("protected", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".maru/maru.db\n.maru/maru.db-*\n.maru/runs/\n.maru/fixture/\n.maru/diff-index\n"
        "tasks/*/artifacts/\ntasks/*/logs/\ntasks/*/rendered/\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_demo.py").write_text("def test_demo():\n    pass\n", encoding="utf-8")
    (root / "tasks" / SLUG / "request.md").write_text(
        "# What I want\n\nShip the change", encoding="utf-8"
    )
    default_agents = """[agents.planner]
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
"""
    (root / "maru.toml").write_text(
        (agents or default_agents)
        + "[limits]\nplan_revisions = 2\nreview_fix_loops = 3\n"
        + '[paths]\nstate_db = ".maru/maru.db"\ntasks = "tasks"\n'
        + extra,
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
    return [
        event.payload for event in _store(root).list_trace(SLUG) if event.type == event_type
    ]


def _run(root: Path, script: dict, *, writes=None, test_runner=None, prompts=None, calls=None):
    calls = calls if calls is not None else []
    prompts = prompts if prompts is not None else []
    return run_relay(
        root,
        SLUG,
        adapter_factory=lambda backend: Scripted(
            backend, script=script, calls=calls, prompts=prompts, writes=writes
        ),
        test_runner=test_runner or (lambda _: (True, "checks ok")),
    )


def _happy_script() -> dict:
    return {
        "planner": [_PLAN],
        "challenger": [_PASS_REVIEW],
        "worker": [_IMPLEMENTATION],
        "reviewer": [_PASS_CODE_REVIEW],
    }


def _document(marker: str, lines: int = 3000) -> str:
    """A ~100 KB generated document, the shape that made review context explode."""
    body = "\n".join(f"| row {index:04d} | value {index:04d} | note {index:04d} |"
                     for index in range(lines))
    return f"# Generated matrix ({marker})\n\n{body}\n"


# --- immutable artifacts -----------------------------------------------------------------


def test_every_planner_revision_keeps_its_own_immutable_artifact(tmp_path) -> None:
    root = _project(tmp_path)
    script = {
        "planner": [_PLAN, _PLAN],
        "challenger": [
            {
                "result": "fail",
                "findings": [
                    {
                        "severity": "blocking",
                        "evidence": "task list",
                        "message": "name the output file",
                        "classification": "BLOCKING_IN_SCOPE",
                        "criterion": "AC1-generated-doc",
                    }
                ],
                "recommendation": "revise",
            },
            _PASS_REVIEW,
        ],
        "worker": [_IMPLEMENTATION],
        "reviewer": [_PASS_CODE_REVIEW],
    }

    _run(root, script, writes={"worker": [{"docs/generated.md": "hello\n"}]})

    history = root / "tasks" / SLUG / "artifacts" / "history"
    assert sorted(path.name for path in (history / "planner").iterdir()) == ["001.json", "002.json"]
    assert sorted(path.name for path in (history / "challenger").iterdir()) == [
        "001.json",
        "002.json",
    ]
    first = json.loads((history / "challenger" / "001.json").read_text(encoding="utf-8"))
    second = json.loads((history / "challenger" / "002.json").read_text(encoding="utf-8"))
    assert first["result"] == "fail" and second["result"] == "pass"
    # The latest pointer still exists for humans and tooling.
    latest = root / "tasks" / SLUG / "artifacts" / "plan-review.json"
    assert json.loads(latest.read_text(encoding="utf-8"))["result"] == "pass"


def test_each_review_iteration_keeps_its_own_immutable_diff_and_artifact(tmp_path) -> None:
    root = _project(tmp_path)
    attempts: list[int] = []

    def gate(_: Path) -> tuple[bool, str]:
        attempts.append(len(attempts))
        return len(attempts) > 1, f"attempt {len(attempts)}"

    _run(
        root,
        _happy_script(),
        writes={"worker": [{"docs/generated.md": "one\n"}, {"docs/generated.md": "two\n"}]},
        test_runner=gate,
    )

    history = root / "tasks" / SLUG / "artifacts" / "history"
    assert sorted(path.name for path in (history / "reviewer").iterdir()) == [
        "001.json",
        "002.json",
    ]
    assert sorted(path.name for path in (history / "worker").iterdir()) == ["001.json", "002.json"]
    assert (history / "review-1" / "full.diff").is_file()
    assert (history / "review-2" / "full.diff").is_file()
    assert (history / "review-2" / "incremental.diff").is_file()
    # Audit history survives: review 1's diff still shows what review 1 actually saw.
    assert "+one" in (history / "review-1" / "full.diff").read_text(encoding="utf-8")
    assert "+two" in (history / "review-2" / "full.diff").read_text(encoding="utf-8")
    rendered = root / "tasks" / SLUG / "rendered"
    assert (rendered / "reviewer-001.md").read_text(encoding="utf-8") != (
        rendered / "reviewer-002.md"
    ).read_text(encoding="utf-8")
    assert (rendered / "reviewer-001.context.json").is_file()


# --- human gate lifecycle ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [("approve", ArcState.MERGED), ("reject", ArcState.REJECTED)],
)
def test_a_resolved_gate_moves_the_arc_to_a_terminal_state(
    tmp_path, monkeypatch, command, expected
) -> None:
    root = _project(tmp_path)
    _run(root, _happy_script(), writes={"worker": [{"docs/generated.md": "hi\n"}]})
    gate = _store(root).list_open_gates()[0]
    monkeypatch.chdir(root)

    result = runner.invoke(app, [command, gate.id])

    assert result.exit_code == 0, result.stdout
    assert expected.value in result.stdout
    arc = _store(root).get_arc(SLUG)
    assert arc is not None
    assert arc.state is expected
    assert arc.current_agent is None
    assert _store(root).list_open_gates() == []
    assert _store(root).list_active_arcs() == []
    assert "No active arc" in runner.invoke(app, ["status"]).stdout
    assert "Inbox empty" in runner.invoke(app, ["inbox"]).stdout
    resolved = _store(root).get_gate(gate.id)
    assert resolved is not None and resolved.resolved_at is not None
    assert resolved.status is (
        GateStatus.APPROVED if command == "approve" else GateStatus.REJECTED
    )


def test_a_delegated_decision_is_authorized_and_audited(tmp_path, monkeypatch) -> None:
    root = _project(
        tmp_path,
        extra=(
            "[delegation]\nenabled = true\nactor = \"DEMO_DELEGATED_HUMAN\"\n"
            "allowed_decisions = [\"approve_nonsemantic_factual_fix\"]\n"
            "forbidden_decisions = [\"remote_push\"]\n"
        ),
    )
    _run(root, _happy_script(), writes={"worker": [{"docs/generated.md": "hi\n"}]})
    gate = _store(root).list_open_gates()[0]
    monkeypatch.chdir(root)

    refused = runner.invoke(app, ["approve", gate.id, "--decision", "remote_push"])
    assert refused.exit_code != 0
    assert _store(root).get_gate(gate.id).status is GateStatus.OPEN

    allowed = runner.invoke(
        app, ["approve", gate.id, "--decision", "approve_nonsemantic_factual_fix"]
    )

    assert allowed.exit_code == 0, allowed.stdout
    delegated = _events(root, "DELEGATED_DECISION")
    assert len(delegated) == 1
    assert delegated[0]["delegated_actor"] == "DEMO_DELEGATED_HUMAN"
    assert delegated[0]["decision"] == "approve_nonsemantic_factual_fix"
    resolved = [event for event in _events(root, "GATE_RESOLVED")]
    assert resolved[-1]["actor"] == "DEMO_DELEGATED_HUMAN"


# --- blocker classification --------------------------------------------------------------


def _blocking(classification: str) -> dict:
    return {
        "result": "fail",
        "findings": [
            {
                "severity": "blocking",
                "evidence": "repo workflow requires a remote check",
                "message": "the frozen Arc forbids what the repository demands",
                "classification": classification,
            }
        ],
        "recommendation": "escalate",
    }


@pytest.mark.parametrize(
    ("classification", "blocker", "gate"),
    [
        ("HUMAN_AUTHORITY_REQUIRED", "HUMAN_AUTHORITY_REQUIRED", True),
        ("CAPABILITY_REQUIRED", "CAPABILITY_MISSING", False),
    ],
)
def test_a_blocker_the_planner_cannot_fix_never_spends_a_revision(
    tmp_path, classification, blocker, gate
) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []

    with pytest.raises(RelayStopped):
        _run(root, {"planner": [_PLAN], "challenger": [_blocking(classification)]}, calls=calls)

    # One plan, one review, then stop: the revision budget is untouched.
    assert [role for role, _ in calls] == ["planner", "challenger"]
    raised = _events(root, "BLOCKER_RAISED")
    assert raised[-1]["blocker"] == blocker
    assert raised[-1]["fixable_by_revision"] is False
    assert bool(_store(root).list_open_gates()) is gate
    arc = _store(root).get_arc(SLUG)
    assert arc is not None and arc.state is ArcState.PAUSED


def test_a_plan_quality_blocker_still_spends_the_revision_budget(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []

    with pytest.raises(RelayStopped, match="Plan revision limit"):
        _run(
            root,
            {"planner": [_PLAN], "challenger": [_blocking("BLOCKING_IN_SCOPE")]},
            calls=calls,
        )

    assert [role for role, _ in calls].count("planner") == 3
    assert _events(root, "BLOCKER_RAISED")[-1]["blocker"] == "RULE_INCOMPLETE"


def test_a_reviewer_finding_needing_human_authority_stops_the_fix_loop(tmp_path) -> None:
    root = _project(tmp_path)
    calls: list[tuple[str, str]] = []

    with pytest.raises(RelayStopped, match="HUMAN_AUTHORITY_REQUIRED"):
        _run(
            root,
            _happy_script()
            | {
                "reviewer": [
                    {
                        "result": "fail",
                        "blocking": [
                            {
                                "file": "docs/generated.md",
                                "location": "1",
                                "evidence": "policy",
                                "message": "only a human may authorize this",
                                "classification": "HUMAN_AUTHORITY_REQUIRED",
                            }
                        ],
                        "non_blocking": [],
                    }
                ]
            },
            writes={"worker": [{"docs/generated.md": "hi\n"}]},
            calls=calls,
        )

    assert [role for role, _ in calls].count("worker") == 1
    assert _events(root, "BLOCKER_RAISED")[-1]["blocker"] == "HUMAN_AUTHORITY_REQUIRED"


# --- provider fallback and evidence -------------------------------------------------------


_FALLBACK_AGENTS = """[agents.planner]
backend = "claude"
permission = "read-only"
[agents.challenger]
backend = "codex"
fallback = ["claude"]
permission = "read-only"
[agents.worker]
backend = "claude"
permission = "workspace-write"
[agents.reviewer]
backend = "codex"
fallback = ["claude"]
permission = "read-only"
"""


def test_provider_quota_exhaustion_falls_back_to_the_configured_provider(tmp_path) -> None:
    root = _project(tmp_path, agents=_FALLBACK_AGENTS)
    calls: list[tuple[str, str]] = []
    script = _happy_script() | {
        "challenger@codex": [Failure("Error: usage limit reached, try again at 3pm")],
        "challenger@claude": [_PASS_REVIEW],
    }

    _run(root, script, writes={"worker": [{"docs/generated.md": "hi\n"}]}, calls=calls)

    assert ("challenger", "codex") in calls and ("challenger", "claude") in calls
    fallback = _events(root, "PROVIDER_FALLBACK")
    assert fallback[0]["role"] == "challenger"
    assert (fallback[0]["from"], fallback[0]["to"]) == ("codex", "claude")
    # The original failure is preserved, not rewritten.
    failed = _events(root, "STAGE_FAILED")
    assert failed[0]["backend"] == "codex"
    assert failed[0]["failure"] == "RESOURCE_EXHAUSTED"
    assert failed[0]["retry_after"] == "3pm"
    completed = [
        event for event in _events(root, "AGENT_COMPLETED") if event["role"] == "challenger"
    ]
    assert completed[0]["backend"] == "claude"
    assert completed[0]["configured_backend"] == "codex"
    assert completed[0]["fallback_used"] is True


def test_a_reviewer_that_falls_back_onto_the_workers_provider_lowers_the_evidence(
    tmp_path,
) -> None:
    root = _project(tmp_path, agents=_FALLBACK_AGENTS)
    script = _happy_script() | {
        "reviewer@codex": [Failure("429 rate limit exceeded")],
        "reviewer@claude": [_PASS_CODE_REVIEW],
    }

    summary = _run(root, script, writes={"worker": [{"docs/generated.md": "hi\n"}]})

    evidence = _events(root, "EVIDENCE_ASSESSED")[-1]
    assert evidence["providers"]["worker"] == "claude"
    assert evidence["providers"]["reviewer"] == "claude"
    assert evidence["evidence_level"] == "PENDING_INDEPENDENT_AUDIT"
    assert "PENDING_INDEPENDENT_AUDIT" in summary.read_text(encoding="utf-8")


def test_a_genuine_cross_provider_review_is_recorded_as_one(tmp_path) -> None:
    root = _project(tmp_path)

    _run(root, _happy_script(), writes={"worker": [{"docs/generated.md": "hi\n"}]})

    assert _events(root, "EVIDENCE_ASSESSED")[-1]["evidence_level"] == "CROSS_PROVIDER_REVIEW"


def test_a_non_retryable_failure_never_silently_uses_the_fallback_provider(tmp_path) -> None:
    root = _project(tmp_path, agents=_FALLBACK_AGENTS)
    calls: list[tuple[str, str]] = []

    with pytest.raises(RelayStopped, match="challenger failed"):
        _run(
            root,
            _happy_script() | {"challenger@codex": [Failure("segmentation fault", exit_code=139)]},
            calls=calls,
        )

    assert ("challenger", "claude") not in calls
    assert _events(root, "PROVIDER_FALLBACK") == []


# --- context projection and incremental review --------------------------------------------


def test_each_role_prompt_carries_only_its_own_projection(tmp_path) -> None:
    root = _project(tmp_path)
    prompts: list[tuple[str, str]] = []

    _run(
        root,
        _happy_script(),
        writes={"worker": [{"docs/generated.md": "hi\n"}]},
        prompts=prompts,
    )

    rendered = dict(prompts)
    assert "## proposed-plan" in rendered["challenger"]
    assert "## diff" not in rendered["challenger"]
    assert "## implementation-report" not in rendered["challenger"]
    assert "## diff" in rendered["reviewer"]
    assert "## request" not in rendered["reviewer"]
    assert "## writable-scope" in rendered["worker"]
    assert "## test-contract" in rendered["worker"]
    # Every packet records what it left out and why.
    manifest = json.loads(
        (root / "tasks" / SLUG / "rendered" / "challenger-001.context.json").read_text(
            encoding="utf-8"
        )
    )
    excluded = [row for row in manifest["sections"] if not row["included"]]
    assert excluded
    assert all("not projected for role challenger" in row["reason"] for row in excluded)
    constitution = next(
        row for row in manifest["sections"] if row["name"] == "constitution"
    )
    assert constitution["sha256"] and constitution["path"].endswith("constitution.md")


def test_a_second_review_of_a_large_document_sends_the_change_not_the_document(tmp_path) -> None:
    """The dogfooding failure: a ~100 KB artifact re-sent in full on every fix iteration."""
    root = _project(
        tmp_path,
        extra="[context]\nmax_packet_bytes = 5000000\nmax_diff_bytes = 5000000\n",
    )
    prompts: list[tuple[str, str]] = []
    attempts: list[int] = []

    def gate(_: Path) -> tuple[bool, str]:
        attempts.append(len(attempts))
        return len(attempts) > 1, f"attempt {len(attempts)}"

    _run(
        root,
        _happy_script(),
        writes={
            "worker": [
                {"docs/generated.md": _document("first")},
                {"docs/generated.md": _document("first").replace("note 0007", "note SEVEN")},
            ]
        },
        test_runner=gate,
        prompts=prompts,
    )

    reviews = [text for role, text in prompts if role == "reviewer"]
    assert len(reviews) == 2
    first, second = len(reviews[0].encode("utf-8")), len(reviews[1].encode("utf-8"))
    assert first > 100_000, "the fixture must reproduce the oversized first review"
    # Structural, not a fragile byte count: the second review is a small fraction of the first.
    assert second < first / 4
    assert "note SEVEN" in reviews[1]
    assert "Incremental review context (iteration 2)" in reviews[1]
    # The full diff is still addressable by path and SHA, so nothing is lost.
    assert "tasks/v02/artifacts/history/review-2/full.diff" in reviews[1]
    assert "sha256=" in reviews[1]
    full = (root / "tasks" / SLUG / "artifacts" / "history" / "review-2" / "full.diff").read_text(
        encoding="utf-8"
    )
    assert len(full.encode("utf-8")) > 100_000


def test_full_review_mode_keeps_the_v0_1_behaviour(tmp_path) -> None:
    root = _project(
        tmp_path,
        extra='[context]\nreview_mode = "full"\nmax_diff_bytes = 5000000\n',
    )
    prompts: list[tuple[str, str]] = []
    attempts: list[int] = []

    def gate(_: Path) -> tuple[bool, str]:
        attempts.append(len(attempts))
        return len(attempts) > 1, f"attempt {len(attempts)}"

    _run(
        root,
        _happy_script(),
        writes={"worker": [{"docs/generated.md": "one\n"}, {"docs/generated.md": "two\n"}]},
        test_runner=gate,
        prompts=prompts,
    )

    reviews = [text for role, text in prompts if role == "reviewer"]
    assert "Incremental review context (iteration" not in reviews[1]
    assert "# Relay changes since baseline" in reviews[1]
    # Cumulative diff of the current worktree: the second write replaced the first.
    assert "+two" in reviews[1]


# --- telemetry ----------------------------------------------------------------------------


def test_the_relay_records_context_cost_per_invocation(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)

    summary = _run(root, _happy_script(), writes={"worker": [{"docs/generated.md": "hi\n"}]})

    completed = _events(root, "AGENT_COMPLETED")
    assert all(event["prompt_bytes"] > 0 for event in completed)
    assert all("duration_s" in event for event in completed)
    assert all(event["tokens"] is None for event in completed if "tokens" in event)
    assert "Context Cost" in summary.read_text(encoding="utf-8")
    monkeypatch.chdir(root)
    cost = runner.invoke(app, ["cost", SLUG])
    assert "Role invocations: 4" in cost.stdout
    assert "Repeated review-loop bytes" in cost.stdout
    status = runner.invoke(app, ["status"])
    assert "CROSS_PROVIDER_REVIEW" in status.stdout
    assert "role projection on" in status.stdout
