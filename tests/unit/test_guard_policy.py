from __future__ import annotations

import pytest

from maru.guard.policy import Decision, decide, review_worker_changes


def test_protected_files_cannot_be_approved_by_a_plan() -> None:
    plan = "Rewrite .maru/constitution.md and maru.toml"

    violations = review_worker_changes([".maru/constitution.md", "maru.toml"], plan)

    assert [violation.split(":")[0] for violation in violations] == [
        "constitution-update",
        "high-risk-security-change",
    ]


def test_unplanned_changes_to_the_grading_rules_are_violations() -> None:
    violations = review_worker_changes(
        ["tests/unit/test_status.py", "pyproject.toml", ".github/workflows/ci.yml"],
        "Implement maru status in src/maru/cli/app.py",
    )

    assert len(violations) == 3
    assert all("unapproved-grading-change" in violation for violation in violations)


def test_only_structured_exact_paths_authorize_grading_changes() -> None:
    path = "tests/unit/test_status.py"
    assert review_worker_changes([path], "Do not modify tests/")
    assert review_worker_changes([path], "Add tests/unit/test_status.py")
    named = review_worker_changes([path], "", writable_paths=[path])
    assert named == []
    assert review_worker_changes([path], "", writable_paths=["tests/"])
    assert review_worker_changes(["pyproject.toml"], "", writable_paths=["pyproject.toml"]) == []


def test_ordinary_source_changes_are_never_violations() -> None:
    assert review_worker_changes(["src/maru/cli/app.py", "README.md"], "Implement status") == []


def test_guard_keeps_main_push_denied_and_deploy_human_gated() -> None:
    assert decide("push-main") is Decision.DENY
    assert decide("deploy") is Decision.ASK
    assert decide("run-tests") is Decision.SAFE


@pytest.mark.parametrize(
    "path",
    [
        "src/maru/core/relay.py",
        "src/maru/core/testgate.py",
        "src/maru/core/inputs.py",
        "src/maru/core/assets.py",
    ],
)
def test_the_relay_control_plane_is_protected_from_agent_edits(path: str) -> None:
    """The relay moved out of scripts/proto_harness.py; its protection moved with it."""
    assert review_worker_changes([path], "plan mentions " + path)


def test_packaged_role_prompts_need_explicit_plan_approval() -> None:
    prompt = "src/maru/assets/prompts/reviewer.md"

    assert review_worker_changes([prompt], "unrelated plan")
    assert review_worker_changes([prompt], "", writable_paths=[prompt]) == []
