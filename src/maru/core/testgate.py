from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from maru.agents.adapters.base import find_executable, run_process


class DeterministicGateError(RuntimeError):
    """The project's deterministic checks are not runnable as configured."""


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    exit_code: int
    elapsed_s: float
    log_path: Path

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def missing_executables(commands: list[list[str]]) -> list[str]:
    """argv[0] values that cannot be resolved on PATH, in declaration order."""
    return [command[0] for command in commands if find_executable(command[0]) is None]


def _slug(argv: list[str]) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(argv))[:60].strip("-") or "command"


def run_test_gate(
    root: Path,
    commands: list[list[str]],
    *,
    logs_dir: Path,
    attempt: int,
    timeout_s: float | None = 300,
) -> tuple[bool, str]:
    """Run every configured check in order and report one combined verdict.

    Rule: run-all, not fail-fast. A failing linter must not hide a failing test suite,
    because the Worker fix loop is bounded and each iteration should see every problem.
    """
    if not commands:
        raise DeterministicGateError(
            "No deterministic checks are configured. Add `[test_gate] commands = [[...]]` "
            "to maru.toml; MARU never lets an agent certify its own work."
        )
    logs_dir.mkdir(parents=True, exist_ok=True)
    results: list[CommandResult] = []
    sections: list[str] = []
    for index, command in enumerate(commands, start=1):
        log_path = logs_dir / f"tests-{attempt}-{index}-{_slug(command)}.log"
        started = time.monotonic()
        try:
            exit_code, stdout, stderr = run_process(list(command), cwd=root, timeout_s=timeout_s)
        except OSError as error:
            exit_code, stdout, stderr = 127, "", f"{error}"
        elapsed = time.monotonic() - started
        header = (
            f"$ {' '.join(command)}\n"
            f"# exit={exit_code} elapsed={elapsed:.3f}s cwd={root}\n"
        )
        log_path.write_text(header + stdout + stderr, encoding="utf-8")
        results.append(CommandResult(list(command), exit_code, elapsed, log_path))
        sections.append(header + stdout + stderr)
    passed = all(result.passed for result in results)
    summary = "\n".join(
        f"{'PASS' if result.passed else 'FAIL'} exit={result.exit_code} "
        f"{result.elapsed_s:.3f}s {' '.join(result.argv)}"
        for result in results
    )
    return passed, f"# Deterministic checks (run-all)\n{summary}\n\n" + "\n".join(sections)
