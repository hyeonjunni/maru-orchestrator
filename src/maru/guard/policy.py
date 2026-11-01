from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from pathlib import PurePosixPath


class Decision(StrEnum):
    SAFE = "SAFE"
    ASK = "ASK"
    DENY = "DENY"


_DENIED = frozenset({"merge-main", "push-main"})
_HUMAN_GATED = frozenset(
    {
        "deploy",
        "destructive-filesystem",
        "credentials",
        "external-transmission",
        "constitution-update",
        "high-risk-security-change",
    }
)


def decide(action: str) -> Decision:
    if action in _DENIED:
        return Decision.DENY
    if action in _HUMAN_GATED:
        return Decision.ASK
    return Decision.SAFE


# Never writable by an agent: a plan cannot approve these, only a human can.
_PROTECTED_FILES = {
    ".maru/constitution.md": "constitution-update",
    "AGENTS.md": "constitution-update",
    "CLAUDE.md": "constitution-update",
    "maru.toml": "high-risk-security-change",
    "scripts/proto_harness.py": "high-risk-security-change",
    "src/maru/core/relay.py": "high-risk-security-change",
    "src/maru/core/testgate.py": "high-risk-security-change",
    "src/maru/core/inputs.py": "high-risk-security-change",
    "src/maru/core/assets.py": "high-risk-security-change",
    "src/maru/guard/policy.py": "high-risk-security-change",
    "src/maru/agents/adapters/base.py": "high-risk-security-change",
    "src/maru/agents/adapters/claude.py": "high-risk-security-change",
    "src/maru/agents/adapters/codex.py": "high-risk-security-change",
}

# The rules that grade the Worker. Writable only when the approved plan names them.
# `src/maru/assets/` holds the packaged role prompts and schemas: what the Reviewer is told.
_GRADED_PREFIXES = ("tests/", ".github/", "src/maru/assets/")
_GRADED_FILES = ("pyproject.toml",)


def protected_scope_text() -> str:
    """The writable scope, spelled out for the Worker instead of left to be inferred.

    The Worker is graded against these rules by MARU Core after it finishes, so telling it the
    rules is cheaper than a fix loop that discovers them.
    """
    protected = "\n".join(
        f"- {path} ({reason})" for path, reason in sorted(_PROTECTED_FILES.items())
    )
    graded = "\n".join(f"- {prefix}" for prefix in (*_GRADED_PREFIXES, *_GRADED_FILES))
    return (
        "Never writable, whatever the plan says:\n"
        f"{protected}\n\n"
        "Writable only when the accepted plan names the exact path, because these decide "
        "whether you pass:\n"
        f"{graded}\n\n"
        "Everything else in the repository is writable within the accepted plan's scope."
    )


def review_worker_changes(changed_paths: Iterable[str], plan_text: str) -> list[str]:
    """Return one human-readable violation per path the Worker should not have changed.

    ``changed_paths`` are repository-relative POSIX paths, as ``git status`` reports them.
    """
    violations: list[str] = []
    for path in sorted(set(changed_paths)):
        if path in _PROTECTED_FILES:
            violations.append(f"{_PROTECTED_FILES[path]}: {path} is protected from agent edits")
        elif _grades_the_worker(path) and not _plan_approves(path, plan_text):
            violations.append(
                f"unapproved-grading-change: {path} decides whether the Worker passes "
                "and the approved plan does not ask for it"
            )
    return violations


def _grades_the_worker(path: str) -> bool:
    return path in _GRADED_FILES or path.startswith(_GRADED_PREFIXES)


def _plan_approves(path: str, plan_text: str) -> bool:
    """True when the plan names the path or a directory containing it."""
    candidate = PurePosixPath(path)
    names = [str(candidate)] + [f"{parent}/" for parent in candidate.parents if str(parent) != "."]
    return any(name in plan_text for name in names)
