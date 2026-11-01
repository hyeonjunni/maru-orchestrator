"""What resolving a Human Gate does to its Arc, for both kinds of gate.

A completion gate opens from HUMAN_APPROVAL. A governance blocker gate opens from PAUSED,
because the relay pauses the Arc before raising the blocker. Dogfooding found the second kind
had no terminal path: rejecting it closed the gate and left the Arc PAUSED with no open
decision and no work to do - active forever, which is the zombie shape the HUMAN_APPROVAL
case was already written to avoid.
"""

from __future__ import annotations

import pytest

from maru.core.models import Arc, ArcState, GateStatus, HumanGate
from maru.storage.sqlite import SqliteStore


def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "maru.db")
    store.initialize()
    return store


def _paused_arc_with_governance_gate(store: SqliteStore) -> HumanGate:
    """An Arc paused by a Planner blocker, with the gate that blocker opened."""
    store.create_arc(Arc(id="arc-1", goal="Edit the authority record"))
    store.transition_arc(
        "arc-1",
        ArcState.PAUSED,
        source="core",
        current_agent="human",
        next_step="Planner raised a blocker: authority required",
    )
    gate = HumanGate(
        id="gate-1",
        arc_id="arc-1",
        reason="HUMAN_AUTHORITY_REQUIRED: Planner raised a blocker: authority required",
    )
    store.create_gate(gate)
    return gate


def _completion_arc_with_gate(store: SqliteStore) -> HumanGate:
    store.create_arc(Arc(id="arc-1", goal="Ship the change", state=ArcState.CODE_REVIEW))
    store.transition_arc(
        "arc-1", ArcState.HUMAN_APPROVAL, source="core", current_agent="human", next_step="Approve"
    )
    gate = HumanGate(id="gate-1", arc_id="arc-1", reason="Approve relay result for demo")
    store.create_gate(gate)
    return gate


def _transitions(store: SqliteStore) -> list[tuple[str, str]]:
    return [
        (event.payload["from"], event.payload["to"])
        for event in store.list_events("arc-1")
        if event.type == "STATE_TRANSITIONED"
    ]


# --- 1. governance gate opened from PAUSED, rejected -----------------------------------------


def test_rejecting_a_governance_gate_ends_the_arc(tmp_path) -> None:
    store = _store(tmp_path)
    _paused_arc_with_governance_gate(store)

    gate, arc = store.resolve_gate("gate-1", GateStatus.REJECTED)

    assert gate.status is GateStatus.REJECTED
    assert gate.resolved_at is not None
    assert arc is not None
    assert arc.state is ArcState.REJECTED
    assert arc.current_agent is None
    assert arc.next_step == "Rejected by human"
    # Terminal means terminal: no open gates, and gone from everything that lists active work.
    assert store.list_open_gates() == []
    assert store.list_active_arcs() == []
    assert ("PAUSED", "REJECTED") in _transitions(store)
    assert any(event.type == "GATE_RESOLVED" for event in store.list_events("arc-1"))


# --- 2. governance gate opened from PAUSED, approved ------------------------------------------


def test_approving_a_governance_gate_grants_authority_without_inventing_a_result(
    tmp_path,
) -> None:
    store = _store(tmp_path)
    _paused_arc_with_governance_gate(store)

    gate, arc = store.resolve_gate("gate-1", GateStatus.APPROVED)

    assert gate.status is GateStatus.APPROVED
    # No work was done, so there is nothing to merge. The Arc stays paused on purpose.
    assert arc is not None and arc.state is ArcState.PAUSED
    assert arc.current_agent == "human"
    assert store.list_open_gates() == []
    assert store.list_active_arcs() != []
    assert ("PAUSED", "REJECTED") not in _transitions(store)
    assert ("PAUSED", "MERGED") not in _transitions(store)
    assert any(event.type == "GATE_RESOLVED" for event in store.list_events("arc-1"))

    # Resuming is how a paused Arc goes back to work, and approval left that path intact.
    assert store.resume_arc("arc-1", source="human").state is ArcState.PLANNING


def test_a_paused_arc_can_never_be_merged_by_a_gate(tmp_path) -> None:
    """MERGED asserts a reviewed implementation exists; a blocked Arc has none."""
    store = _store(tmp_path)
    _paused_arc_with_governance_gate(store)

    store.resolve_gate("gate-1", GateStatus.APPROVED)

    arc = store.get_arc("arc-1")
    assert arc is not None and arc.state is not ArcState.MERGED
    with pytest.raises(ValueError, match="Invalid Arc transition: PAUSED -> MERGED"):
        store.transition_arc("arc-1", ArcState.MERGED, source="human")


# --- 3 and 4. the completion gate lifecycle is untouched --------------------------------------


def test_approving_a_completion_gate_still_merges(tmp_path) -> None:
    store = _store(tmp_path)
    _completion_arc_with_gate(store)

    gate, arc = store.resolve_gate("gate-1", GateStatus.APPROVED)

    assert gate.status is GateStatus.APPROVED
    assert arc is not None
    assert arc.state is ArcState.MERGED
    assert arc.current_agent is None
    assert arc.next_step == "Approved by human gate"
    assert store.list_active_arcs() == []
    assert ("HUMAN_APPROVAL", "MERGED") in _transitions(store)


def test_rejecting_a_completion_gate_still_rejects(tmp_path) -> None:
    store = _store(tmp_path)
    _completion_arc_with_gate(store)

    gate, arc = store.resolve_gate("gate-1", GateStatus.REJECTED)

    assert gate.status is GateStatus.REJECTED
    assert arc is not None
    assert arc.state is ArcState.REJECTED
    assert arc.current_agent is None
    assert arc.next_step == "Rejected by human"
    assert store.list_active_arcs() == []
    assert ("HUMAN_APPROVAL", "REJECTED") in _transitions(store)


@pytest.mark.parametrize("status", [GateStatus.APPROVED, GateStatus.REJECTED])
def test_a_gate_on_any_other_state_still_moves_nothing(tmp_path, status) -> None:
    """Unchanged rule: resolving a gate is not a general way to move an Arc."""
    store = _store(tmp_path)
    store.create_arc(Arc(id="arc-1", goal="Ship a vertical slice"))
    store.create_gate(HumanGate(id="gate-1", arc_id="arc-1", reason="Review changes"))

    _, arc = store.resolve_gate("gate-1", status)

    assert arc is not None and arc.state is ArcState.PLANNING
    assert _transitions(store) == []
