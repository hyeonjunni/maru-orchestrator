from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from maru.agents.adapters.base import find_executable, resolve_command
from maru.agents.adapters.claude import ClaudeAdapter
from maru.agents.adapters.codex import CodexAdapter
from maru.cli.app import _tool_version
from maru.core.models import AgentRequest

MISSING = "maru-definitely-not-installed-binary"
ENVELOPE = '{"session_id": "shim-session", "structured_output": {"ok": true}}'


def _install_shim(directory: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put the launcher shape this OS actually uses on PATH: a .cmd shim on Windows."""
    if os.name == "nt":
        shim = directory / "maru_shim.cmd"
        shim.write_text(f"@echo off\r\necho {ENVELOPE}\r\n", encoding="utf-8")
    else:
        shim = directory / "maru_shim"
        shim.write_text(f"#!/bin/sh\necho '{ENVELOPE}'\n", encoding="utf-8")
        shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return shim


def test_find_executable_resolves_platform_shim_to_an_absolute_path(tmp_path, monkeypatch) -> None:
    shim = _install_shim(tmp_path, monkeypatch)

    resolved = find_executable("maru_shim")

    assert resolved is not None
    assert Path(resolved).is_absolute()
    assert Path(resolved) == shim  # on Windows this is the .cmd, found via PATHEXT


def test_adapter_launches_a_bare_name_through_the_resolved_path(tmp_path, monkeypatch) -> None:
    """S1 regression: Popen(["maru_shim"]) raises WinError 2 when the shim is a .cmd."""
    _install_shim(tmp_path, monkeypatch)
    adapter = ClaudeAdapter(command=["maru_shim"])

    assert Path(adapter.command[0]).is_absolute()

    result = adapter.run(AgentRequest(role="planner", prompt="hi"), cwd=tmp_path)

    assert result.exit_code == 0
    assert result.structured_result == {"ok": True}
    assert result.session_id == "shim-session"


def test_resolved_executable_is_an_absolute_path_for_both_adapters(tmp_path, monkeypatch) -> None:
    _install_shim(tmp_path, monkeypatch)

    assert ClaudeAdapter(command=["maru_shim"]).command[0] == CodexAdapter(
        command=["maru_shim"]
    ).command[0]


def test_absolute_executable_path_is_used_verbatim_with_its_arguments() -> None:
    adapter = CodexAdapter(command=[sys.executable, "-c", "pass"])

    assert adapter.command == (os.path.abspath(sys.executable), "-c", "pass")


def test_missing_executable_fails_loudly_at_construction() -> None:
    assert find_executable(MISSING) is None
    with pytest.raises(FileNotFoundError, match=MISSING):
        resolve_command([MISSING])
    with pytest.raises(FileNotFoundError, match=MISSING):
        ClaudeAdapter(command=[MISSING])
    with pytest.raises(FileNotFoundError, match=MISSING):
        CodexAdapter(command=[MISSING])


def test_doctor_and_adapter_launch_agree_on_availability(tmp_path, monkeypatch) -> None:
    assert _tool_version(MISSING) == "not found"

    _install_shim(tmp_path, monkeypatch)

    assert _tool_version("maru_shim") != "not found"
    assert ClaudeAdapter(command=["maru_shim"]).command[0] == find_executable("maru_shim")


def test_doctor_reports_a_version_probe_timeout(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert "timed out" in _tool_version(sys.executable)
