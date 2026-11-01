from __future__ import annotations

from maru.core.models import GateStatus, HumanGate, utc_now

DEFAULT_CONSTITUTION = """1. Agent cannot merge/push main by default.
2. Agent cannot modify Constitution without explicit human approval.
3. No hidden model memory may be required to resume an Arc.
4. Important decisions must be externally inspectable.
5. Planner/Worker/Reviewer exchange artifacts rather than shared chat histories.
6. Dangerous actions require executor-level gating.
7. Learning-plane context must never be injected into Production history.
"""


def resolve(gate: HumanGate, status: GateStatus) -> HumanGate:
    if gate.status is not GateStatus.OPEN:
        raise ValueError(f"Gate {gate.id} is already {gate.status.value}")
    if status is GateStatus.OPEN:
        raise ValueError("An open gate must resolve to APPROVED or REJECTED")
    return gate.model_copy(update={"status": status, "resolved_at": utc_now()})
