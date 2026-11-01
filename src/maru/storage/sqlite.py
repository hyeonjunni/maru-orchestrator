from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from maru.core.gates import resolve
from maru.core.models import TERMINAL_STATES, Arc, ArcState, GateStatus, HumanGate
from maru.core.state_machine import transition
from maru.events.models import MaruEvent
from maru.storage.migrations import SCHEMA_SQL, SCHEMA_VERSION


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def create_arc(self, arc: Arc, *, event: MaruEvent | None = None) -> None:
        """Insert an Arc and, in the same transaction, the event that records its creation."""
        data = arc.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO arcs
                (id, goal, state, current_agent, next_step, created_at, updated_at)
                VALUES
                (:id, :goal, :state, :current_agent, :next_step, :created_at, :updated_at)""",
                data,
            )
            if event is not None:
                self._insert_event(connection, event)

    def get_arc(self, arc_id: str) -> Arc | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
        return Arc.model_validate(dict(row)) if row else None

    def list_active_arcs(self) -> list[Arc]:
        terminal = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ", ".join("?" * len(terminal))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM arcs WHERE state NOT IN ({placeholders}) ORDER BY updated_at DESC",
                terminal,
            ).fetchall()
        return [Arc.model_validate(dict(row)) for row in rows]

    def transition_arc(
        self,
        arc_id: str,
        target: ArcState,
        *,
        source: str,
        current_agent: str | None = None,
        next_step: str | None = None,
    ) -> Arc:
        """Move an Arc to ``target``, recording who is working and what comes next."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
            if row is None:
                raise KeyError(f"Arc not found: {arc_id}")
            updated = self._transition_locked(
                connection,
                Arc.model_validate(dict(row)),
                target,
                source,
                current_agent,
                next_step,
            )
        return updated

    def resume_arc(self, arc_id: str, *, source: str) -> Arc:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
            if row is None:
                raise KeyError(f"Arc not found: {arc_id}")
            current = Arc.model_validate(dict(row))
            if current.state is not ArcState.PAUSED:
                raise ValueError(f"Arc {arc_id} is not PAUSED")
            if connection.execute(
                "SELECT 1 FROM gates WHERE arc_id = ? AND status = ? LIMIT 1",
                (arc_id, GateStatus.OPEN.value),
            ).fetchone():
                raise ValueError(f"Arc {arc_id} has an open human gate; approve or reject it first")
            rows = connection.execute(
                "SELECT payload FROM events WHERE arc_id = ? AND type = ? ORDER BY rowid DESC",
                (arc_id, "STATE_TRANSITIONED"),
            ).fetchall()
            target = next(
                (
                    ArcState(payload["from"])
                    for event_row in rows
                    if (payload := json.loads(event_row["payload"])).get("to") == "PAUSED"
                ),
                ArcState.PLANNING,
            )
            return self._transition_locked(
                connection,
                current,
                target,
                source,
                current.current_agent,
                current.next_step,
            )

    def _transition_locked(
        self,
        connection: sqlite3.Connection,
        current: Arc,
        target: ArcState,
        source: str,
        current_agent: str | None,
        next_step: str | None,
    ) -> Arc:
        updated = transition(current, target).model_copy(
            update={"current_agent": current_agent, "next_step": next_step}
        )
        connection.execute(
            "UPDATE arcs SET state = ?, current_agent = ?, next_step = ?, updated_at = ? "
            "WHERE id = ?",
            (
                updated.state.value,
                updated.current_agent,
                updated.next_step,
                updated.updated_at.isoformat(),
                updated.id,
            ),
        )
        self._insert_event(
            connection,
            MaruEvent(
                arc_id=current.id,
                source=source,
                type="STATE_TRANSITIONED",
                payload={"from": current.state.value, "to": target.value},
            ),
        )
        return updated

    def append_event(self, event: MaruEvent) -> None:
        with self._connect() as connection:
            self._insert_event(connection, event)

    @staticmethod
    def _insert_event(connection: sqlite3.Connection, event: MaruEvent) -> None:
        data = event.model_dump(mode="json")
        data["payload"] = json.dumps(data["payload"], ensure_ascii=False)
        data["artifact_refs"] = json.dumps(data["artifact_refs"], ensure_ascii=False)
        connection.execute(
            """INSERT INTO events
            (event_id, arc_id, run_id, timestamp, source, type, payload, artifact_refs,
             parent_event_id)
            VALUES (:event_id, :arc_id, :run_id, :timestamp, :source, :type, :payload,
                    :artifact_refs, :parent_event_id)""",
            data,
        )

    def list_events(self, arc_id: str) -> list[MaruEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE arc_id = ? ORDER BY rowid", (arc_id,)
            ).fetchall()
        events = []
        for row in rows:
            data = dict(row)
            data["payload"] = json.loads(data["payload"])
            data["artifact_refs"] = json.loads(data["artifact_refs"])
            events.append(MaruEvent.model_validate(data))
        return events

    def list_trace(self, identifier: str) -> list[MaruEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM events
                WHERE arc_id = ? OR run_id = ?
                ORDER BY rowid""",
                (identifier, identifier),
            ).fetchall()
        events = []
        for row in rows:
            data = dict(row)
            data["payload"] = json.loads(data["payload"])
            data["artifact_refs"] = json.loads(data["artifact_refs"])
            events.append(MaruEvent.model_validate(data))
        return events

    def create_gate(self, gate: HumanGate) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO gates (id, arc_id, reason, status, created_at, resolved_at)
                VALUES (:id, :arc_id, :reason, :status, :created_at, :resolved_at)""",
                gate.model_dump(mode="json"),
            )

    def get_gate(self, gate_id: str) -> HumanGate | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
        return HumanGate.model_validate(dict(row)) if row else None

    def list_open_gates(self, arc_id: str | None = None) -> list[HumanGate]:
        query = "SELECT * FROM gates WHERE status = ?"
        params: tuple[str, ...] = (GateStatus.OPEN.value,)
        if arc_id is not None:
            query += " AND arc_id = ?"
            params += (arc_id,)
        query += " ORDER BY created_at, id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [HumanGate.model_validate(dict(row)) for row in rows]

    def resolve_gate(
        self, gate_id: str, status: GateStatus, *, actor: str = "human"
    ) -> tuple[HumanGate, Arc | None]:
        """Close a gate and move its Arc, in one transaction.

        A gate that is resolved but leaves its Arc in HUMAN_APPROVAL is a zombie: `maru status`
        would keep reporting an Arc waiting on a decision that was already made. So the decision
        and the state change either both land or neither does.

        A governance blocker opens its gate while the Arc is already PAUSED, and that case is
        deliberately asymmetric:

        * Rejecting it ends the Arc. A refused request is exactly what REJECTED means, and
          leaving it PAUSED produced the same zombie in a different state - closed gate, no
          open decision, active forever.
        * Approving it grants the authority the agent lacked and nothing more. No work was
          done, so there is no result to merge; the Arc stays PAUSED and returns to work
          through `resume_arc`, which is already how a paused Arc resumes.

        Any other state is untouched, as before: resolving a gate is not a general way to move
        an Arc.
        """
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
            if row is None:
                raise KeyError(f"Gate not found: {gate_id}")
            gate = resolve(HumanGate.model_validate(dict(row)), status)
            connection.execute(
                "UPDATE gates SET status = ?, resolved_at = ? WHERE id = ?",
                (
                    gate.status.value,
                    gate.resolved_at.isoformat() if gate.resolved_at else None,
                    gate.id,
                ),
            )
            self._insert_event(
                connection,
                MaruEvent(
                    arc_id=gate.arc_id,
                    source=actor,
                    type="GATE_RESOLVED",
                    payload={"gate_id": gate.id, "status": gate.status.value, "actor": actor},
                ),
            )
            arc_row = connection.execute(
                "SELECT * FROM arcs WHERE id = ?", (gate.arc_id,)
            ).fetchone()
            arc = Arc.model_validate(dict(arc_row)) if arc_row else None
            if arc is not None and arc.state is ArcState.HUMAN_APPROVAL:
                target = (
                    ArcState.MERGED if status is GateStatus.APPROVED else ArcState.REJECTED
                )
                arc = self._transition_locked(
                    connection,
                    arc,
                    target,
                    actor,
                    None,
                    "Approved by human gate" if target is ArcState.MERGED else "Rejected by human",
                )
            elif (
                arc is not None
                and arc.state is ArcState.PAUSED
                and status is GateStatus.REJECTED
            ):
                arc = self._transition_locked(
                    connection, arc, ArcState.REJECTED, actor, None, "Rejected by human"
                )
        return gate, arc
