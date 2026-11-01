from __future__ import annotations

import pytest
from pydantic import ValidationError

from maru.core.config import MaruConfig
from maru.core.models import (
    Arc,
    ImplementationArtifact,
    PlanReviewArtifact,
    ReviewArtifact,
)


def test_passing_reviews_cannot_contain_blocking_findings() -> None:
    with pytest.raises(ValidationError):
        PlanReviewArtifact.model_validate(
            {
                "result": "pass",
                "findings": [
                    {"severity": "blocking", "evidence": "risk", "message": "must fix"}
                ],
                "recommendation": "continue",
            }
        )
    with pytest.raises(ValidationError):
        ReviewArtifact.model_validate(
            {
                "result": "pass",
                "blocking": [
                    {"file": "x.py", "location": "1", "evidence": "bug", "message": "fix"}
                ],
            }
        )


def test_blank_goals_and_negative_limits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Arc(goal="   ")
    with pytest.raises(ValidationError):
        MaruConfig.model_validate(
            {"agents": {}, "limits": {"plan_revisions": -1, "review_fix_loops": 0}}
        )


def test_role_identity_is_not_coupled_to_a_backend() -> None:
    config = MaruConfig.model_validate(
        {
            "agents": {
                "worker": {"backend": "codex", "permission": "workspace-write"},
                "reviewer": {"backend": "claude", "permission": "read-only"},
            }
        }
    )

    assert config.agents["worker"].backend == "codex"
    assert config.agents["reviewer"].backend == "claude"


def test_implementation_artifact_reports_expected_tests_not_executed_ones() -> None:
    artifact = ImplementationArtifact.model_validate(
        {
            "changed_files": ["src/maru/cli/app.py"],
            "notes": ["Rendered the status table"],
            "tests_expected": ["tests/integration/test_cli.py"],
            "unresolved_risks": [],
        }
    )

    assert artifact.tests_expected == ["tests/integration/test_cli.py"]
    assert not hasattr(artifact, "tests")
