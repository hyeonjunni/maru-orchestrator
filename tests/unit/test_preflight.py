from __future__ import annotations

import sys

import pytest

from maru.core.config import AgentSettings, MaruConfig
from maru.core.relay import capability_problems


class _Adapter:
    def run(self, *args, **kwargs):  # pragma: no cover - never invoked in preflight
        raise AssertionError("preflight only constructs adapters")


def _config(**gate: object) -> MaruConfig:
    return MaruConfig.model_validate(
        {
            "agents": {
                "planner": {"backend": "claude", "permission": "read-only"},
                "challenger": {"backend": "codex", "permission": "read-only"},
                "worker": {"backend": "claude", "permission": "workspace-write"},
                "reviewer": {"backend": "codex", "permission": "read-only"},
            },
            "test_gate": gate,
        }
    )


def _ok_factory(_: str) -> _Adapter:
    return _Adapter()


def test_a_runnable_environment_reports_no_blockers() -> None:
    config = _config(commands=[[sys.executable, "-c", "pass"]])

    assert capability_problems(config, adapter_factory=_ok_factory, gate_is_configured=False) == []


def test_an_unconfigured_gate_blocks_the_worker() -> None:
    problems = capability_problems(
        _config(), adapter_factory=_ok_factory, gate_is_configured=False
    )

    assert problems == ["no deterministic checks configured; add `[test_gate] commands = [[...]]` "
                        "to maru.toml"]


def test_an_injected_runner_satisfies_the_gate_requirement() -> None:
    assert capability_problems(_config(), adapter_factory=_ok_factory, gate_is_configured=True) == (
        []
    )


def test_an_unresolvable_check_executable_blocks_the_worker() -> None:
    config = _config(commands=[["maru-no-such-tool"], [sys.executable, "-c", "pass"]])

    problems = capability_problems(
        config, adapter_factory=_ok_factory, gate_is_configured=False
    )

    assert problems == ["test_gate command not on PATH: maru-no-such-tool"]


def test_an_unavailable_worker_backend_blocks_the_worker() -> None:
    def factory(backend: str) -> _Adapter:
        if backend == "claude":
            raise FileNotFoundError("executable not found on PATH: claude")
        return _Adapter()

    problems = capability_problems(_config(), adapter_factory=factory, gate_is_configured=True)

    assert problems == ["worker backend claude unavailable: executable not found on PATH: claude"]


def test_an_unavailable_reviewer_backend_blocks_the_worker() -> None:
    def factory(backend: str) -> _Adapter:
        if backend == "codex":
            raise FileNotFoundError("no codex")
        return _Adapter()

    problems = capability_problems(_config(), adapter_factory=factory, gate_is_configured=True)

    assert problems == ["reviewer backend codex unavailable: no codex"]


def test_a_missing_role_backend_blocks_the_worker() -> None:
    config = MaruConfig(
        agents={"planner": AgentSettings(backend="claude", permission="read-only")}
    )

    problems = capability_problems(config, adapter_factory=_ok_factory, gate_is_configured=True)

    assert problems == ["no backend configured for worker", "no backend configured for reviewer"]


def test_a_missing_git_blocks_the_worker(monkeypatch) -> None:
    monkeypatch.setenv("MARU_GIT_BIN", "maru-no-such-git")

    problems = capability_problems(_config(), adapter_factory=_ok_factory, gate_is_configured=True)

    assert problems == ["git is not executable: maru-no-such-git"]


@pytest.mark.parametrize("gate_is_configured", [True, False])
def test_preflight_never_launches_an_adapter(gate_is_configured: bool) -> None:
    """Capability only: constructing the adapter proves the executable resolves."""
    config = _config(commands=[[sys.executable, "-c", "pass"]])

    capability_problems(
        config, adapter_factory=_ok_factory, gate_is_configured=gate_is_configured
    )
