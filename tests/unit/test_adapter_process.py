from __future__ import annotations

import sys
import time

import pytest

from maru.agents.adapters.base import execute, no_redaction, prepare_run
from maru.core.models import AgentRequest


def test_interrupted_process_is_reaped_before_control_returns(tmp_path, monkeypatch) -> None:
    from maru.agents.adapters import base

    original = base.subprocess.Popen.communicate
    processes = []

    def interrupt_once(process, *args, **kwargs):
        if not processes:
            processes.append(process)
            raise KeyboardInterrupt
        return original(process, *args, **kwargs)

    monkeypatch.setattr(base.subprocess.Popen, "communicate", interrupt_once)
    try:
        with pytest.raises(KeyboardInterrupt):
            base.run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path
            )
        assert processes[0].poll() is not None
    finally:
        # Keep the failing regression from leaving its own process behind.
        if processes and processes[0].poll() is None:
            base._kill_process_tree(processes[0])
            original(processes[0])


def test_agent_process_timeout_is_bounded(tmp_path) -> None:
    sentinel = tmp_path / "orphan-ran"
    child = (
        "import time; from pathlib import Path; time.sleep(1); "
        f"Path({str(sentinel)!r}).write_text('orphan')"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
    )
    request = AgentRequest(role="planner", prompt="wait")
    files = prepare_run(tmp_path, request)
    started = time.monotonic()

    output = execute(
        [sys.executable, "-c", parent],
        request,
        cwd=tmp_path,
        timeout_s=0.1,
        files=files,
        redactor=no_redaction,
    )

    assert output.exit_code == 124
    assert time.monotonic() - started < 5
    assert "timed out" in output.stderr
    time.sleep(1.2)
    assert not sentinel.exists()
