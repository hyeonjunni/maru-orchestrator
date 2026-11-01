from __future__ import annotations

import json
from pathlib import Path

import pytest

from maru.core.assets import resolve_prompt, resolve_schema

# Prompts and schemas ship inside the package, so these read the packaged assets rather
# than a copy in the repository root.
ROOT = Path(__file__).resolve().parents[2]
PLANNER = resolve_prompt(ROOT, "planner").text.lower()
CHALLENGER = resolve_prompt(ROOT, "challenger").text.lower()


def _has_all(text: str, *terms: str) -> bool:
    return all(term in text for term in terms)


def test_planner_assigns_deterministic_test_execution_to_core() -> None:
    assert _has_all(PLANNER, "maru core", "test gate")
    assert "test-gate artifact" in PLANNER


@pytest.mark.parametrize(
    "term",
    [
        "relay artifacts",
        "task-directory bookkeeping",
        "manifest",
        "arc/event persistence",
        "humangate",
        "retry/revision accounting",
    ],
)
def test_planner_disowns_relay_bookkeeping(term: str) -> None:
    assert term in PLANNER


@pytest.mark.parametrize(
    "term",
    ["git baseline capture", "diff attribution", "guard enforcement", "worker mutation detection"],
)
def test_planner_disowns_git_and_guard_enforcement(term: str) -> None:
    assert term in PLANNER


def test_planner_forbids_inventing_control_plane_tasks() -> None:
    assert "do not own" in PLANNER
    assert "never create implementation tasks" in PLANNER
    # The regression case: T6 wrote an artifact under tasks/ while T7 hashed tasks/.
    assert _has_all(PLANNER, "writes a test-gate artifact under `tasks/`", "computes a manifest")


def test_planner_boundary_is_contextual_not_a_word_ban() -> None:
    assert "contextual" in PLANNER
    assert "explicitly asks to change maru's" in PLANNER


def test_planner_revision_rule_prefers_removal_over_compensation() -> None:
    assert "revise only the defect" in PLANNER
    assert "delete the meta-check" in PLANNER
    assert "proportional" in PLANNER


def test_challenger_may_still_fail_a_plan() -> None:
    assert "fail" in CHALLENGER
    assert "correctness" in CHALLENGER


def test_planning_schemas_unchanged() -> None:
    plan = json.loads(resolve_schema(ROOT, "planner").text)
    # Every property is required: OpenAI strict structured outputs, which Codex uses for
    # `--output-schema`, rejects an object whose `required` omits any key in `properties`.
    assert plan["required"] == [
        "goal",
        "assumptions",
        "tasks",
        "acceptance_criteria",
        "risks",
        "blocking_surface",
        "blocker",
    ]
    assert plan["additionalProperties"] is False
    assert plan["properties"]["tasks"]["items"]["required"] == ["id", "description", "depends_on"]

    review = json.loads(resolve_schema(ROOT, "challenger").text)
    assert review["required"] == ["result", "findings", "recommendation"]
    assert review["properties"]["result"]["enum"] == ["pass", "fail"]
