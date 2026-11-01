from __future__ import annotations

import sqlite3

import pytest

from maru.core.models import Arc, ArcState, GateStatus, HumanGate
from maru.core.state_machine import transition
from maru.events.models import MaruEvent
from maru.storage.sqlite import SqliteStore


def test_invalid_state_jump_is_rejected() -> None:
    arc = Arc(id="arc-1", goal="Ship a vertical slice")

    with pytest.raises(ValueError, match="PLANNING -> IMPLEMENTING"):
        transition(arc, ArcState.IMPLEMENTING)


def test_transition_updates_arc_and_appends_event(tmp_path) -> None:
    store = SqliteStore(tmp_path / "maru.db")
    store.initialize()
    store.create_arc(Arc(id="arc-1", goal="Ship a vertical slice"))

    updated = store.transition_arc("arc-1", ArcState.PLAN_REVIEW, source="planner")

    assert updated.state is ArcState.PLAN_REVIEW
    events = store.list_events("arc-1")
    assert [(event.source, event.type, event.payload) for event in events] == [
        (
            "planner",
            "STATE_TRANSITIONED",
            {"from": "PLANNING", "to": "PLAN_REVIEW"},
        )
    ]


def test_initialize_is_idempotent_and_events_are_append_only(tmp_path) -> None:
    database = tmp_path / "maru.db"
    store = SqliteStore(database)
    store.initialize()
    store.initialize()
    store.create_arc(Arc(id="arc-1", goal="Ship a vertical slice"))
    store.append_event(
        MaruEvent(
            event_id="event-1",
            arc_id="arc-1",
            run_id="run-1",
            source="core",
            type="CREATED",
        )
    )

    with sqlite3.connect(database) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute("UPDATE events SET type = 'CHANGED' WHERE event_id = 'event-1'")


def test_gate_resolution_removes_gate_from_inbox(tmp_path) -> None:
    store = SqliteStore(tmp_path / "maru.db")
    store.initialize()
    store.create_arc(Arc(id="arc-1", goal="Ship a vertical slice"))
    store.create_gate(HumanGate(id="gate-1", arc_id="arc-1", reason="Review changes"))

    assert [gate.id for gate in store.list_open_gates()] == ["gate-1"]

    resolved, arc = store.resolve_gate("gate-1", GateStatus.APPROVED)

    assert resolved.status is GateStatus.APPROVED
    assert store.list_open_gates() == []
    # This Arc is in PLANNING, not HUMAN_APPROVAL, so resolving a gate does not move it.
    assert arc is not None and arc.state is ArcState.PLANNING
    assert [(event.type, event.payload) for event in store.list_events("arc-1")] == [
        ("GATE_RESOLVED", {"gate_id": "gate-1", "status": "APPROVED", "actor": "human"})
    ]


def test_resume_returns_to_the_state_recorded_before_pause(tmp_path) -> None:
    store = SqliteStore(tmp_path / "maru.db")
    store.initialize()
    store.create_arc(Arc(id="arc-1", goal="Continue work", state=ArcState.IMPLEMENTING))
    store.transition_arc("arc-1", ArcState.PAUSED, source="human")

    resumed = store.resume_arc("arc-1", source="human")

    assert resumed.state is ArcState.IMPLEMENTING
