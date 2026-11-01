from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from maru.core.models import AgentRequest, utc_now

Redactor = Callable[[str], str]


def no_redaction(value: str) -> str:
    return value


_FENCE = re.compile(r"\A```[A-Za-z0-9_-]*[ \t]*\n(?P<body>.*?)\n?```\Z", re.DOTALL)


def json_object(value: str) -> dict[str, Any] | None:
    """Parse a JSON object, tolerating surrounding whitespace and one markdown fence."""
    text = value.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group("body").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def find_executable(name: str) -> str | None:
    """Absolute path for a command name, or None. Windows PATHEXT picks up .cmd/.bat shims."""
    resolved = shutil.which(name)
    # abspath, not resolve(): a node CLI on PATH is often a symlink to a .js file.
    return os.path.abspath(resolved) if resolved else None


def resolve_command(command: Sequence[str]) -> tuple[str, ...]:
    """Resolve argv[0] once, so Popen gets a full path instead of a bare name."""
    name, *args = command
    executable = find_executable(name)
    if executable is None:
        raise FileNotFoundError(f"executable not found on PATH: {name}")
    return (executable, *args)


@dataclass(frozen=True)
class RunFiles:
    prompt: Path
    stdout: Path
    stderr: Path
    last_message: Path


@dataclass(frozen=True)
class ProcessOutput:
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime


def prepare_run(cwd: Path, request: AgentRequest) -> RunFiles:
    run_dir = cwd / ".maru" / "runs" / str(uuid4())
    run_dir.mkdir(parents=True, exist_ok=False)
    prompt = run_dir / "rendered-prompt.md"
    prompt.write_text(request.prompt, encoding="utf-8")
    return RunFiles(
        prompt=prompt,
        stdout=run_dir / "stdout.log",
        stderr=run_dir / "stderr.log",
        last_message=run_dir / "last-message.json",
    )


def execute(
    command: Sequence[str],
    request: AgentRequest,
    *,
    cwd: Path,
    timeout_s: float | None,
    files: RunFiles,
    redactor: Redactor,
) -> ProcessOutput:
    started_at = utc_now()
    exit_code, stdout, stderr = run_process(
        command, cwd=cwd, input_text=request.prompt, timeout_s=timeout_s
    )
    finished_at = utc_now()
    stdout = redactor(stdout)
    stderr = redactor(stderr)
    files.stdout.write_text(stdout, encoding="utf-8")
    files.stderr.write_text(stderr, encoding="utf-8")
    return ProcessOutput(exit_code, stdout, stderr, started_at, finished_at)


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    process = subprocess.Popen(  # noqa: S603 - argv is constructed without a shell
        list(command),
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if os.name == "nt"
        else 0,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_s)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        detail = f"{stderr}\nProcess timed out after {timeout_s} seconds".strip()
        return 124, stdout, detail


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        if not system_root.is_absolute():
            system_root = Path(r"C:\Windows")
        taskkill = system_root / "System32" / "taskkill.exe"
        try:
            result = subprocess.run(  # noqa: S603
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if result.returncode != 0 and process.poll() is None:
                _break_windows_group(process)
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                _break_windows_group(process)
    else:
        try:
            getattr(os, "killpg")(process.pid, getattr(signal, "SIGKILL"))  # noqa: B009
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def _break_windows_group(process: subprocess.Popen[str]) -> None:
    try:
        process.send_signal(getattr(signal, "CTRL_BREAK_EVENT"))  # noqa: B009
    except OSError:
        pass
