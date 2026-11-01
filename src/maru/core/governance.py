"""Typed blockers, evidence levels and delegated human authority.

Three questions MARU v0.1 could not answer, all of them governance rather than mechanics:

1. *Who* can fix this blocker, and does trying again cost a Planner revision?
2. How independent is the evidence that says this Arc is good?
3. Was this decision made by the human, or by an actor the human delegated to?
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel, Field

from maru.agents.failures import FailureKind


class BlockerClass(StrEnum):
    """Why an Arc stopped. The class, not the message, decides what happens next."""

    RULE_INCOMPLETE = "RULE_INCOMPLETE"
    RULE_AMBIGUOUS = "RULE_AMBIGUOUS"
    ORDERING_CONTRADICTION = "ORDERING_CONTRADICTION"
    AUTHORITY_CONFUSION = "AUTHORITY_CONFUSION"
    INPUT_MISSING = "INPUT_MISSING"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    HUMAN_AUTHORITY_REQUIRED = "HUMAN_AUTHORITY_REQUIRED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    OTHER = "OTHER"


class BlockerPolicy(NamedTuple):
    owner: str
    fixable_by_revision: bool
    retryable: bool
    # True when a human must *decide* something, which is what a Human Gate records. A missing
    # executable or a stale snapshot is not a decision: it is fixed and the relay is rerun, so
    # it pauses the Arc without manufacturing a gate nobody can meaningfully approve.
    requires_decision: bool = False


# Only plan-quality blockers may spend a Planner revision. A missing executable, a governance
# conflict or an exhausted provider quota is not made better by rewriting the plan, and the
# dogfooding run proved that spending revisions on them just burns the budget before the real
# problem reaches a human.
_POLICY: dict[BlockerClass, BlockerPolicy] = {
    BlockerClass.RULE_INCOMPLETE: BlockerPolicy("planner", True, True),
    BlockerClass.RULE_AMBIGUOUS: BlockerPolicy("planner", True, True),
    BlockerClass.ORDERING_CONTRADICTION: BlockerPolicy("planner", True, True),
    BlockerClass.AUTHORITY_CONFUSION: BlockerPolicy("human", False, False, True),
    BlockerClass.INPUT_MISSING: BlockerPolicy("human", False, True),
    BlockerClass.CAPABILITY_MISSING: BlockerPolicy("human", False, True),
    BlockerClass.HUMAN_AUTHORITY_REQUIRED: BlockerPolicy("human", False, False, True),
    BlockerClass.RESOURCE_EXHAUSTED: BlockerPolicy("core", False, True),
    BlockerClass.OTHER: BlockerPolicy("human", False, False),
}

_FROM_FAILURE = {
    FailureKind.RESOURCE_EXHAUSTED: BlockerClass.RESOURCE_EXHAUSTED,
    FailureKind.AUTH: BlockerClass.CAPABILITY_MISSING,
    FailureKind.SCHEMA: BlockerClass.RULE_INCOMPLETE,
    FailureKind.PROCESS: BlockerClass.CAPABILITY_MISSING,
    FailureKind.TIMEOUT: BlockerClass.RESOURCE_EXHAUSTED,
}


def policy_for(blocker: BlockerClass) -> BlockerPolicy:
    return _POLICY[blocker]


def from_failure(kind: FailureKind) -> BlockerClass:
    """Map an adapter process failure onto the governance vocabulary."""
    return _FROM_FAILURE[kind]


def blocker_payload(blocker: BlockerClass, reason: str) -> dict[str, object]:
    policy = policy_for(blocker)
    return {
        "blocker": blocker.value,
        "reason": reason,
        "owner": policy.owner,
        "fixable_by_revision": policy.fixable_by_revision,
        "retryable": policy.retryable,
        "requires_decision": policy.requires_decision,
    }


class FindingClass(StrEnum):
    """How a Challenger or Reviewer finding relates to the frozen blocking surface."""

    BLOCKING_IN_SCOPE = "BLOCKING_IN_SCOPE"
    NON_BLOCKING = "NON_BLOCKING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    HUMAN_AUTHORITY_REQUIRED = "HUMAN_AUTHORITY_REQUIRED"
    CAPABILITY_REQUIRED = "CAPABILITY_REQUIRED"


_ESCALATED = {
    FindingClass.HUMAN_AUTHORITY_REQUIRED: BlockerClass.HUMAN_AUTHORITY_REQUIRED,
    FindingClass.CAPABILITY_REQUIRED: BlockerClass.CAPABILITY_MISSING,
}


def escalation_for(finding: FindingClass) -> BlockerClass | None:
    """The blocker a finding escalates to, or None when the Planner can just revise."""
    return _ESCALATED.get(finding)


class EvidenceLevel(StrEnum):
    """How much independent confirmation stands behind an Arc's result.

    The provider-comparison levels describe a *reviewed implementation*. Two levels exist
    because an Arc can end well without one: `BLOCKED_NO_IMPLEMENTATION` when a typed blocker
    stopped the relay, and `INTENTIONAL_NOOP_COMPLETION` when the relay ran to the end and the
    correct answer was to change nothing. Neither is a reviewed implementation, and neither may
    borrow a provider-comparison level to look like one.
    """

    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"
    SAME_PROVIDER_REVIEW = "SAME_PROVIDER_REVIEW"
    CROSS_PROVIDER_REVIEW = "CROSS_PROVIDER_REVIEW"
    PENDING_INDEPENDENT_AUDIT = "PENDING_INDEPENDENT_AUDIT"
    VERIFIED = "VERIFIED"
    # The Arc stopped on a typed blocker. Nothing was implemented, so nothing was reviewed;
    # what the audit trail supports is the *decision*, not an implementation.
    BLOCKED_NO_IMPLEMENTATION = "BLOCKED_NO_IMPLEMENTATION"
    # The relay completed, the gate passed and the Reviewer passed - on an empty change set.
    # A legitimate outcome, but the Reviewer reviewed an absence, not an implementation.
    INTENTIONAL_NOOP_COMPLETION = "INTENTIONAL_NOOP_COMPLETION"


def evidence_level(
    *,
    providers: dict[str, str],
    tests_passed: bool,
    require_independent_review: bool,
    work_performed: bool = True,
    blocked: bool = False,
) -> EvidenceLevel:
    """What the relay actually proved, given who really ran each role and whether work happened.

    ``providers`` maps role to the backend that produced its artifact, which is the backend
    after any fallback - never the one `maru.toml` merely asked for. A reviewer that fell back
    onto the worker's own provider is a same-provider review and must not be dressed up as an
    independent one.

    ``blocked`` is true when a typed blocker ended the Arc, and ``work_performed`` is false when
    the relay changed no outcome-relevant path. Both are checked before any provider comparison:
    two providers agreeing that nothing was implemented is not a cross-provider review of an
    implementation, and the dogfooding run proved that calling it one misleads the human who
    reads `maru status` instead of the diff.
    """
    if blocked:
        return EvidenceLevel.BLOCKED_NO_IMPLEMENTATION
    reviewer = providers.get("reviewer")
    if reviewer is None:
        return EvidenceLevel.DETERMINISTIC_ONLY
    if not work_performed:
        return EvidenceLevel.INTENTIONAL_NOOP_COMPLETION
    worker = providers.get("worker")
    if reviewer == worker:
        return (
            EvidenceLevel.PENDING_INDEPENDENT_AUDIT
            if require_independent_review
            else EvidenceLevel.SAME_PROVIDER_REVIEW
        )
    if not tests_passed:
        return EvidenceLevel.DETERMINISTIC_ONLY
    return EvidenceLevel.CROSS_PROVIDER_REVIEW


class DelegationSettings(BaseModel):
    """Bounded standing authority a human grants to another actor. Never autopilot."""

    enabled: bool = False
    actor: str = ""
    expires_at: datetime | None = None
    allowed_decisions: list[str] = Field(default_factory=list)
    forbidden_decisions: list[str] = Field(default_factory=list)


def authorize_delegated(
    delegation: DelegationSettings, decision: str, *, now: datetime | None = None
) -> str | None:
    """Why this delegated decision is refused, or None when it is within the granted scope."""
    moment = now or datetime.now(UTC)
    if not delegation.enabled or not delegation.actor:
        return "Delegation is not enabled; add [delegation] to maru.toml or decide as the human"
    if delegation.expires_at is not None:
        expiry = delegation.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= moment:
            return f"Delegation to {delegation.actor} expired at {expiry.isoformat()}"
    if decision in delegation.forbidden_decisions:
        return f"Decision {decision!r} is explicitly forbidden for {delegation.actor}"
    if decision not in delegation.allowed_decisions:
        return f"Decision {decision!r} is not in the delegated scope for {delegation.actor}"
    return None


def delegation_record(
    delegation: DelegationSettings,
    decision: str,
    gate_id: str,
    outcome: str,
    *,
    result_observed: bool = True,
) -> dict[str, object]:
    """The audit row for one delegated decision. Recorded, never inferred later."""
    return {
        "delegated_actor": delegation.actor,
        "decision": decision,
        "gate_id": gate_id,
        "outcome": outcome,
        "allowed_decisions": list(delegation.allowed_decisions),
        "forbidden_decisions": list(delegation.forbidden_decisions),
        "expires_at": delegation.expires_at.isoformat() if delegation.expires_at else None,
        "decided_at": datetime.now(UTC).isoformat(),
        "result_observed_before_decision": result_observed,
    }
