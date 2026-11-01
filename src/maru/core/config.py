from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from maru.core.governance import DelegationSettings

Backend = Literal["claude", "codex"]


class ConfigError(ValueError):
    """Invalid project configuration, safe to display without its input values."""


class AgentSettings(BaseModel):
    backend: Backend
    permission: Literal["read-only", "workspace-write"]
    # Providers to try, in order, when the primary fails with a retryable resource error.
    # Empty by default: v0.1 behaviour is "one provider, then stop".
    fallback: list[Backend] = Field(default_factory=list)


class ProviderPolicySettings(BaseModel):
    allow_fallback: bool = True
    # A reviewer that fell back onto the worker's provider is not an independent review, and
    # saying so out loud is the whole point of the evidence level.
    require_independent_review_for_verified: bool = True


class ContextSettings(BaseModel):
    """How much of the durable record each role's prompt is allowed to carry."""

    max_packet_bytes: int = Field(default=80_000, gt=0)
    max_diff_bytes: int = Field(default=50_000, gt=0)
    review_mode: Literal["incremental", "full"] = "incremental"
    role_projection: bool = True


class LimitSettings(BaseModel):
    plan_revisions: int = Field(default=2, ge=0)
    review_fix_loops: int = Field(default=3, ge=0)


class PathSettings(BaseModel):
    state_dir: Path = Path(".maru")
    state_db: Path = Path(".maru/maru.db")
    tasks: Path = Path("tasks")


class TestGateSettings(BaseModel):
    """Ordered deterministic project checks, as argv arrays. Never a shell string."""

    commands: list[list[str]] = Field(default_factory=list)

    @field_validator("commands")
    @classmethod
    def commands_are_argv(cls, value: list[list[str]]) -> list[list[str]]:
        for index, command in enumerate(value):
            if not command or not command[0].strip():
                raise ValueError(f"test_gate.commands[{index}] needs a non-empty executable")
        return value


class MaruConfig(BaseModel):
    agents: dict[str, AgentSettings]
    limits: LimitSettings = LimitSettings()
    paths: PathSettings = PathSettings()
    test_gate: TestGateSettings = TestGateSettings()
    provider_policy: ProviderPolicySettings = ProviderPolicySettings()
    context: ContextSettings = ContextSettings()
    delegation: DelegationSettings = DelegationSettings()


_DEFAULT_AGENTS = {
    "planner": AgentSettings(backend="claude", permission="read-only"),
    "challenger": AgentSettings(backend="codex", permission="read-only"),
    "worker": AgentSettings(backend="claude", permission="workspace-write"),
    "reviewer": AgentSettings(backend="codex", permission="read-only"),
}


def load_config(root: Path) -> MaruConfig:
    path = root / "maru.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(
            "Cannot read maru.toml; check file access, UTF-8 and TOML syntax"
        ) from error
    agents = data.get("agents", {})
    if isinstance(agents, dict):
        data["agents"] = {**_DEFAULT_AGENTS, **agents}
    try:
        config = MaruConfig.model_validate(data)
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors())
        raise ConfigError(f"Invalid maru.toml configuration fields: {fields}") from error
    project = root.resolve()
    for field in ("state_dir", "state_db", "tasks"):
        value = getattr(config.paths, field)
        windows_path = PureWindowsPath(value)
        try:
            target = (project / value).resolve()
        except (OSError, ValueError, RuntimeError) as error:
            raise ConfigError(f"Invalid maru.toml paths.{field}: cannot resolve path") from error
        if (
            value.is_absolute()
            or windows_path.drive
            or windows_path.root
            or ".." in windows_path.parts
            or any(part.casefold() == ".git" for part in windows_path.parts)
            or target == project
            or not target.is_relative_to(project)
            or any(part.casefold() == ".git" for part in target.relative_to(project).parts)
        ):
            raise ConfigError(
                f"Invalid maru.toml paths.{field}: use a project-relative path outside .git"
            )
    return config


def maru_owned(config: MaruConfig) -> Callable[[str], bool]:
    """Predicate for repository-relative POSIX paths MARU itself writes.

    Only the exact configured state directory, state database and task directory count.
    Nothing else is exempted, so a MARU file can never make a sibling source file invisible
    to the clean-tree baseline.
    """
    directories = tuple(
        f"{path.as_posix().rstrip('/')}/" for path in (config.paths.state_dir, config.paths.tasks)
    )
    database = config.paths.state_db.as_posix()

    def owned(path: str) -> bool:
        return path.startswith(directories) or path == database or path.startswith(f"{database}-")

    return owned
