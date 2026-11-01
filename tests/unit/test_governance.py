from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from maru.agents.failures import FailureKind
from maru.core.governance import (
    BlockerClass,
    DelegationSettings,
    EvidenceLevel,
    FindingClass,
    authorize_delegated,
    delegation_record,
    escalation_for,
    evidence_level,
    from_failure,
    policy_for,
)


@pytest.mark.parametrize(
    "blocker",
    [
        BlockerClass.HUMAN_AUTHORITY_REQUIRED,
        BlockerClass.CAPABILITY_MISSING,
        BlockerClass.RESOURCE_EXHAUSTED,
        BlockerClass.INPUT_MISSING,
        BlockerClass.AUTHORITY_CONFUSION,
    ],
)
def test_blockers_outside_the_planners_reach_never_spend_a_revision(blocker) -> None:
    assert policy_for(blocker).fixable_by_revision is False


@pytest.mark.parametrize(
    "blocker",
    [
        BlockerClass.RULE_INCOMPLETE,
        BlockerClass.RULE_AMBIGUOUS,
        BlockerClass.ORDERING_CONTRADICTION,
    ],
)
def test_plan_quality_blockers_are_the_only_ones_that_spend_a_revision(blocker) -> None:
    policy = policy_for(blocker)
    assert policy.fixable_by_revision is True
    assert policy.owner == "planner"


def test_only_a_real_decision_opens_a_human_gate() -> None:
    assert policy_for(BlockerClass.HUMAN_AUTHORITY_REQUIRED).requires_decision is True
    assert policy_for(BlockerClass.AUTHORITY_CONFUSION).requires_decision is True
    # Fix the environment and rerun: there is nothing for a human to approve or reject.
    assert policy_for(BlockerClass.CAPABILITY_MISSING).requires_decision is False
    assert policy_for(BlockerClass.RESOURCE_EXHAUSTED).requires_decision is False


def test_provider_quota_exhaustion_is_a_retryable_core_blocker() -> None:
    assert from_failure(FailureKind.RESOURCE_EXHAUSTED) is BlockerClass.RESOURCE_EXHAUSTED
    policy = policy_for(BlockerClass.RESOURCE_EXHAUSTED)
    assert (policy.owner, policy.retryable, policy.fixable_by_revision) == ("core", True, False)


def test_findings_escalate_only_when_the_planner_cannot_legally_fix_them() -> None:
    assert escalation_for(FindingClass.BLOCKING_IN_SCOPE) is None
    assert escalation_for(FindingClass.NON_BLOCKING) is None
    assert escalation_for(FindingClass.OUT_OF_SCOPE) is None
    assert (
        escalation_for(FindingClass.HUMAN_AUTHORITY_REQUIRED)
        is BlockerClass.HUMAN_AUTHORITY_REQUIRED
    )
    assert escalation_for(FindingClass.CAPABILITY_REQUIRED) is BlockerClass.CAPABILITY_MISSING


def test_a_reviewer_on_the_workers_own_provider_is_not_an_independent_review() -> None:
    same = evidence_level(
        providers={"worker": "claude", "reviewer": "claude"},
        tests_passed=True,
        require_independent_review=True,
    )
    assert same is EvidenceLevel.PENDING_INDEPENDENT_AUDIT
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "claude"},
            tests_passed=True,
            require_independent_review=False,
        )
        is EvidenceLevel.SAME_PROVIDER_REVIEW
    )


def test_cross_provider_review_requires_a_different_provider_and_a_green_gate() -> None:
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "codex"},
            tests_passed=True,
            require_independent_review=True,
        )
        is EvidenceLevel.CROSS_PROVIDER_REVIEW
    )
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "codex"},
            tests_passed=False,
            require_independent_review=True,
        )
        is EvidenceLevel.DETERMINISTIC_ONLY
    )
    assert (
        evidence_level(providers={"worker": "claude"}, tests_passed=True,
                       require_independent_review=True)
        is EvidenceLevel.DETERMINISTIC_ONLY
    )


def _delegation(**overrides) -> DelegationSettings:
    data = {
        "enabled": True,
        "actor": "DEMO_DELEGATED_HUMAN",
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "allowed_decisions": ["approve_nonsemantic_factual_fix"],
        "forbidden_decisions": ["remote_push"],
    }
    return DelegationSettings.model_validate(data | overrides)


def test_delegated_decisions_are_bounded_by_scope_time_and_explicit_prohibition() -> None:
    assert authorize_delegated(_delegation(), "approve_nonsemantic_factual_fix") is None
    assert "not in the delegated scope" in str(authorize_delegated(_delegation(), "submission"))
    assert "explicitly forbidden" in str(authorize_delegated(_delegation(), "remote_push"))
    expired = _delegation(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    assert "expired" in str(authorize_delegated(expired, "approve_nonsemantic_factual_fix"))
    off = _delegation(enabled=False)
    assert "not enabled" in str(authorize_delegated(off, "approve_nonsemantic_factual_fix"))


def test_the_delegation_audit_row_records_who_decided_what_under_which_authority() -> None:
    record = delegation_record(
        _delegation(), "approve_nonsemantic_factual_fix", "gate-1", "APPROVED"
    )

    assert record["delegated_actor"] == "DEMO_DELEGATED_HUMAN"
    assert record["decision"] == "approve_nonsemantic_factual_fix"
    assert record["gate_id"] == "gate-1"
    assert record["outcome"] == "APPROVED"
    assert record["forbidden_decisions"] == ["remote_push"]
    assert record["result_observed_before_decision"] is True
    assert record["decided_at"]


def test_a_blocked_arc_reports_the_decision_not_a_reviewed_implementation() -> None:
    """The dogfooding bug: providers differing is not review of work that never happened."""
    assert (
        evidence_level(
            providers={"planner": "claude", "challenger": "codex"},
            tests_passed=False,
            require_independent_review=True,
            blocked=True,
        )
        is EvidenceLevel.BLOCKED_NO_IMPLEMENTATION
    )
    # `blocked` wins even when every other signal looks like a healthy cross-provider Arc.
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "codex"},
            tests_passed=True,
            require_independent_review=True,
            work_performed=True,
            blocked=True,
        )
        is EvidenceLevel.BLOCKED_NO_IMPLEMENTATION
    )


def test_a_zero_change_arc_is_a_no_op_completion_not_a_cross_provider_review() -> None:
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "codex"},
            tests_passed=True,
            require_independent_review=True,
            work_performed=False,
        )
        is EvidenceLevel.INTENTIONAL_NOOP_COMPLETION
    )


def test_work_that_really_happened_still_earns_the_provider_comparison_levels() -> None:
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "codex"},
            tests_passed=True,
            require_independent_review=True,
            work_performed=True,
        )
        is EvidenceLevel.CROSS_PROVIDER_REVIEW
    )
    # Provider fallback landed the reviewer on the worker's own provider: unchanged behaviour.
    assert (
        evidence_level(
            providers={"worker": "claude", "reviewer": "claude"},
            tests_passed=True,
            require_independent_review=True,
            work_performed=True,
        )
        is EvidenceLevel.PENDING_INDEPENDENT_AUDIT
    )
