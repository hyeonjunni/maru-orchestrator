from __future__ import annotations

import sys
import time

from maru.agents.adapters.base import execute, no_redaction, prepare_run
from maru.core.models import AgentRequest


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
