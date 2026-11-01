from __future__ import annotations

from maru.core.models import Arc, ArcState, utc_now

_ALLOWED: dict[ArcState, frozenset[ArcState]] = {
    ArcState.PLANNING: frozenset({ArcState.PLAN_REVIEW, ArcState.FAILED, ArcState.PAUSED}),
    ArcState.PLAN_REVIEW: frozenset(
        {ArcState.PLANNING, ArcState.IMPLEMENTING, ArcState.FAILED, ArcState.PAUSED}
    ),
    ArcState.IMPLEMENTING: frozenset({ArcState.TESTING, ArcState.FAILED, ArcState.PAUSED}),
    ArcState.TESTING: frozenset(
        {ArcState.CODE_REVIEW, ArcState.IMPLEMENTING, ArcState.FAILED, ArcState.PAUSED}
    ),
    ArcState.CODE_REVIEW: frozenset(
        {ArcState.IMPLEMENTING, ArcState.HUMAN_APPROVAL, ArcState.FAILED, ArcState.PAUSED}
    ),
    ArcState.HUMAN_APPROVAL: frozenset(
        {
            ArcState.MERGED,
            ArcState.REJECTED,
            ArcState.IMPLEMENTING,
            ArcState.FAILED,
            ArcState.PAUSED,
        }
    ),
    ArcState.MERGED: frozenset(),
    ArcState.REJECTED: frozenset(),
    ArcState.FAILED: frozenset(),
    # A paused Arc goes back to the state it paused from, which is what `maru resume` does.
    # REJECTED is the one terminal state it may also reach directly: a governance blocker opens
    # its Human Gate while the Arc is already PAUSED, and a human refusing that gate has ended
    # the Arc. Without it the gate closes and the Arc stays active forever with nothing to do.
    # MERGED is deliberately absent: approving a blocker grants authority, it does not make the
    # unwritten implementation exist.
    ArcState.PAUSED: frozenset(
        {
            ArcState.PLANNING,
            ArcState.PLAN_REVIEW,
            ArcState.IMPLEMENTING,
            ArcState.TESTING,
            ArcState.CODE_REVIEW,
            ArcState.HUMAN_APPROVAL,
            ArcState.REJECTED,
            ArcState.FAILED,
        }
    ),
}


def transition(arc: Arc, target: ArcState) -> Arc:
    if target not in _ALLOWED[arc.state]:
        raise ValueError(f"Invalid Arc transition: {arc.state.value} -> {target.value}")
    return arc.model_copy(update={"state": target, "updated_at": utc_now()})
