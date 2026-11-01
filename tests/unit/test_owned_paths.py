from __future__ import annotations

import pytest

from maru.core.config import MaruConfig, maru_owned


def _owned(**paths: str):
    return maru_owned(MaruConfig(agents={}, paths=paths or {}))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    [
        ".maru/constitution.md",
        ".maru/runs/abc/stdout.log",
        ".maru/maru.db",
        ".maru/maru.db-wal",
        ".maru/maru.db-shm",
        "tasks/first-relay/request.md",
        "tasks/first-relay/inputs/spec.md",
    ],
)
def test_maru_bookkeeping_is_owned(path: str) -> None:
    assert _owned()(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "tests/test_demo.py",
        ".maruvian/app.py",
        "tasks_helper.py",
        "src/.maru/app.py",
        "docs/tasks/plan.md",
        ".maru.py",
    ],
)
def test_project_source_is_never_owned(path: str) -> None:
    """A MARU-looking prefix must never exempt a sibling source file from the baseline."""
    assert not _owned()(path)


def test_ownership_follows_the_configured_paths() -> None:
    owned = _owned(state_dir="var/maru", state_db="var/maru/state.db", tasks="var/maru/work")

    assert owned("var/maru/state.db-wal")
    assert owned("var/maru/work/slug/request.md")
    assert not owned(".maru/constitution.md")
    assert not owned("tasks/slug/request.md")
