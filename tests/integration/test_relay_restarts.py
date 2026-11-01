from __future__ import annotations

import subprocess
import sys

import pytest

from maru.core.models import Arc, ArcState, HumanGate
from maru.core.relay import RelayStopped, run_relay, start_run
from maru.storage.sqlite import SqliteStore
from tests.integration.test_harness import ScriptedAdapter, _project


def test_request_reuse_preserves_original_bytes(tmp_path):
    task = start_run(tmp_path, "demo", goal="Original request")
    original = (task / "request.md").read_bytes()
    with pytest.raises(RelayStopped, match="different request"):
        start_run(tmp_path, "demo", goal="Replacement")
    assert (task / "request.md").read_bytes() == original
    assert start_run(tmp_path, "demo", goal="Original request") == task


@pytest.mark.parametrize("state", [ArcState.PAUSED, ArcState.HUMAN_APPROVAL])
def test_open_gate_prevents_rerun_without_touching_events(tmp_path, state):
    root = _project(tmp_path)
    store = SqliteStore(root / ".maru/maru.db")
    store.initialize()
    store.create_arc(Arc(id="first-relay", goal="Finish status", state=state))
    store.create_gate(HumanGate(arc_id="first-relay", reason="Human must decide"))
    calls = []
    with pytest.raises(RelayStopped, match="open human gate"):
        run_relay(root, "first-relay", adapter_factory=lambda b: ScriptedAdapter(b, calls, True))
    assert calls == []
    assert store.get_arc("first-relay").state == state
    assert store.list_events("first-relay") == []


def test_open_gate_prevents_resume(tmp_path):
    store = SqliteStore(tmp_path / "state.db")
    store.initialize()
    store.create_arc(Arc(id="demo", goal="Do work", state=ArcState.PAUSED))
    store.create_gate(HumanGate(arc_id="demo", reason="Human must decide"))
    with pytest.raises(ValueError, match="open human gate"):
        store.resume_arc("demo", source="human")
    assert store.get_arc("demo").state is ArcState.PAUSED


def test_restart_preserves_numbered_evidence(tmp_path):
    root = _project(tmp_path, revisions=0)
    factory = lambda backend: ScriptedAdapter(backend, [], True)  # noqa: E731
    for index in range(2):
        with pytest.raises(RelayStopped, match="Review fix limit"):
            run_relay(
                root,
                "first-relay",
                adapter_factory=factory,
                test_runner=lambda _, index=index: (False, f"failure from run {index}"),
            )
        task = root / "tasks/first-relay"
        if index == 0:
            originals = {
                path: path.read_bytes()
                for folder in (task / "artifacts/history", task / "rendered", task / "logs")
                for path in folder.rglob("*")
                if path.is_file() and (folder.name != "rendered" or "-00" in path.name)
            }
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert (task / "artifacts/history/planner/002.json").is_file()
    assert (task / "artifacts/history/review-8/full.diff").is_file()
    assert "failure from run 0" in (task / "logs/tests-1.log").read_text()
    assert "failure from run 1" in (task / "logs/tests-5.log").read_text()


def test_project_lock_rejects_other_process_and_releases_on_error(tmp_path):
    from maru.core.relay import project_lock

    script = """
import sys
from pathlib import Path
from maru.core.relay import start_run, RelayStopped
try:
    start_run(Path(sys.argv[1]), 'other', goal='Other work')
except RelayStopped:
    sys.exit(2)
"""
    with pytest.raises(RuntimeError, match="interrupted"):
        with project_lock(tmp_path):
            result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=False)
            assert result.returncode == 2
            assert not (tmp_path / "tasks/other/request.md").exists()
            raise RuntimeError("interrupted")
    assert start_run(tmp_path, "other", goal="Other work").is_dir()


def test_check_mutation_stops_before_a_worker_can_hide_a_grading_edit(tmp_path):
    root = _project(tmp_path)
    writes = [{"helper.py": "VALUE = 1\n"}, {"tests/test_demo.py": "# checks removed\n"}]

    def gate(project):
        (project / "tests/test_demo.py").write_text("def test_demo():\n    assert False\n")
        return False, "failed"

    with pytest.raises(RelayStopped, match="checks modified"):
        run_relay(
            root,
            "first-relay",
            adapter_factory=lambda b: ScriptedAdapter(b, [], True, worker_writes=writes),
            test_runner=gate,
        )
    assert len(writes) == 1  # The second Worker is never invoked.


def test_approval_state_without_a_gate_cannot_restart_planning(tmp_path):
    root = _project(tmp_path)
    store = SqliteStore(root / ".maru/maru.db")
    store.initialize()
    store.create_arc(Arc(id="first-relay", goal="Finish status", state=ArcState.HUMAN_APPROVAL))
    calls = []
    with pytest.raises(RelayStopped, match="HUMAN_APPROVAL"):
        run_relay(root, "first-relay", adapter_factory=lambda b: ScriptedAdapter(b, calls, True))
    assert calls == []
    assert store.get_arc("first-relay").state is ArcState.HUMAN_APPROVAL
    assert store.list_events("first-relay") == []
