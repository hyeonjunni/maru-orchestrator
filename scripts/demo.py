"""Offline CLI demo: synthetic agents, real state transitions and a Python test gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from maru.agents.adapters.base import prepare_run
from maru.cli import app as cli_module
from maru.core import relay
from maru.core.models import AgentRequest, AgentResult, ArcState, utc_now
from maru.storage.sqlite import SqliteStore

GOAL = "Add greeting.py with greet() returning hello, MARU"


@contextmanager
def isolated_git_environment(project: Path) -> Iterator[None]:
    """Keep inherited Git targets, configuration and hooks out of the demo."""
    saved = {
        key: value
        for key, value in os.environ.items()
        if key.startswith("GIT_") or key == "MARU_GIT_BIN"
    }
    empty = project / ".maru" / "empty-git-config"
    empty.mkdir(parents=True)
    for key in saved:
        del os.environ[key]
    overrides = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TEMPLATE_DIR": str(empty),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": str(empty),
    }
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key in overrides:
            os.environ.pop(key, None)
        os.environ.update(saved)


class SyntheticAdapter:
    """Fixed example artifacts; never launches a provider or evaluates a model."""

    def __init__(self, backend: str, rejected: list[bool]) -> None:
        self.backend = backend
        self.rejected = rejected

    def run(
        self, request: AgentRequest, *, cwd: Path, timeout_s: float | None = None
    ) -> AgentResult:
        outputs: dict[str, dict[str, Any]] = {
            "planner": {
                "goal": GOAL,
                "tasks": [{"id": "greeting", "description": GOAL}],
                "acceptance_criteria": ["greet() returns hello, MARU"],
            },
            "challenger": {"result": "pass", "recommendation": "Implement the greeting"},
            "worker": {"changed_files": ["greeting.py"], "tests_expected": ["check.py"]},
            "reviewer": {"result": "pass", "blocking": [], "non_blocking": []},
        }
        if request.role == "challenger" and not self.rejected:
            self.rejected.append(True)
            outputs["challenger"] = {
                "result": "fail",
                "recommendation": "Synthetic failure to demonstrate restart",
                "findings": [
                    {
                        "severity": "blocking",
                        "evidence": "Synthetic demo scenario",
                        "message": "Demonstrate a bounded plan rejection",
                    }
                ],
            }
        if request.role == "worker":
            (cwd / "greeting.py").write_text(
                'def greet():\n    return "hello, MARU"\n', encoding="utf-8"
            )
        files = prepare_run(cwd, request)
        files.prompt.write_text(request.prompt, encoding="utf-8")
        payload = outputs[request.role]
        raw = json.dumps(payload)
        files.stdout.write_text(raw, encoding="utf-8")
        files.stderr.write_text("", encoding="utf-8")
        now = utc_now()
        return AgentResult(
            backend=f"synthetic-{self.backend}",
            role=request.role,
            exit_code=0,
            stdout=raw,
            stderr="",
            structured_result=payload,
            started_at=now,
            finished_at=now,
            rendered_prompt_path=files.prompt,
            raw_log_path=files.stdout,
            stderr_path=files.stderr,
        )


def demonstrate(project: Path) -> None:
    (project / ".gitignore").write_text(".maru/\ntasks/\n__pycache__/\n", encoding="utf-8")
    (project / "check.py").write_text(
        'from greeting import greet\nassert greet() == "hello, MARU"\n'
        'print("greeting check passed")\n',
        encoding="utf-8",
    )
    (project / "maru.toml").write_text(
        "[limits]\nplan_revisions = 0\nreview_fix_loops = 0\n"
        "[test_gate]\ncommands = " + json.dumps([[sys.executable, "check.py"]]) + "\n",
        encoding="utf-8",
    )
    for args in (
        ["init", "-q"],
        ["add", "--", ".gitignore", "check.py", "maru.toml"],
        [
            "-c",
            "user.name=MARU demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "Synthetic demo baseline",
        ],
    ):
        subprocess.run(["git", *args], cwd=project, capture_output=True, check=True)

    previous_cwd = Path.cwd()
    previous_factory = relay.default_adapter_factory
    previous_console = cli_module.console
    rejected: list[bool] = []
    runner = CliRunner()

    def command(*args: str, expected: int = 0) -> str:
        result = runner.invoke(cli_module.app, list(args))
        print("$ maru " + " ".join(args))
        print(result.output.replace(str(project), "<demo-project>").strip())
        if result.exit_code != expected:
            raise RuntimeError(
                f"Expected exit {expected}, got {result.exit_code}"
            ) from result.exception
        return result.output

    try:
        os.chdir(project)
        relay.default_adapter_factory = lambda backend: SyntheticAdapter(backend, rejected)
        cli_module.console = Console(width=100, force_terminal=False)
        command("init")
        command("run", GOAL, "--slug", "greeting", expected=2)
        command("status")
        store = SqliteStore(project / ".maru/maru.db")
        first = project / "tasks/greeting/artifacts/history/planner/001.json"
        original = first.read_bytes()
        command("resume", "greeting")
        command("run", GOAL, "--slug", "greeting")
        assert first.read_bytes() == original
        assert (first.parent / "002.json").is_file()
        assert "greeting check passed" in (project / "tasks/greeting/logs/tests-1.log").read_text(
            encoding="utf-8"
        )
        command("status")
        command("inbox")
        command("run", GOAL, "--slug", "greeting", expected=2)
        gate = store.list_open_gates("greeting")[0]
        print("Demo-only approval of synthetic work (live workflows require your decision).")
        command("approve", gate.id)
        arc = store.get_arc("greeting")
        assert arc is not None and arc.state is ArcState.MERGED
        assert not store.list_open_gates("greeting")
        assert len([e for e in store.list_events("greeting") if e.type == "ARC_CREATED"]) == 1
        command("status")
        print("DEMO PASS: PAUSED -> replan -> HUMAN_APPROVAL -> MERGED")
        print("Numbered evidence preserved. No model was contacted; provider labels are simulated.")
        print("Inspect with: maru trace greeting (from the demo project).")
    finally:
        relay.default_adapter_factory = previous_factory
        cli_module.console = previous_console
        os.chdir(previous_cwd)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="New or empty directory for demo evidence")
    args = parser.parse_args()
    project = (
        args.directory.resolve() if args.directory else Path(tempfile.mkdtemp(prefix="maru-demo-"))
    )
    if project.exists() and (not project.is_dir() or any(project.iterdir())):
        parser.error("directory must be empty; existing user files are never overwritten")
    project.mkdir(parents=True, exist_ok=True)
    print("SYNTHETIC OFFLINE DEMO: no provider processes, credentials, network or API charges.")
    with isolated_git_environment(project):
        demonstrate(project)
    print(f"Local evidence directory: {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
