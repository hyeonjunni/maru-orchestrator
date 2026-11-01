from __future__ import annotations

import hashlib
from pathlib import Path

from maru.core import context


def _sections() -> list[context.Section]:
    return [
        context.Section(
            name=context.CONSTITUTION, text="rules", reason="authority", required=True
        ),
        context.Section(name=context.REQUEST, text="do the thing", reason="ask", required=True),
        context.Section(name=context.PROPOSED_PLAN, text='{"goal": "x"}', reason="under review"),
        context.Section(name=context.DIFF, text="diff --git a/x b/x", reason="what changed"),
        context.Section(name=context.IMPLEMENTATION_REPORT, text="{}", reason="worker report"),
    ]


def test_each_role_receives_only_the_sections_its_task_needs() -> None:
    pool = _sections()

    packets = {
        role: context.project(role, pool, max_packet_bytes=100_000)
        for role in ("planner", "challenger", "worker", "reviewer")
    }

    included = {
        role: {record.name for record in packet.sections if record.included}
        for role, packet in packets.items()
    }
    # The Challenger reviews a plan, not an implementation; the Reviewer grades a diff, not the
    # historical request-to-plan handoff.
    assert context.DIFF not in included["challenger"]
    assert context.IMPLEMENTATION_REPORT not in included["challenger"]
    assert context.PROPOSED_PLAN in included["challenger"]
    assert context.DIFF in included["reviewer"]
    assert context.REQUEST not in included["reviewer"]
    assert context.DIFF not in included["planner"]
    assert all(context.CONSTITUTION in names for names in included.values())


def test_an_excluded_section_is_recorded_with_its_reason_not_silently_dropped() -> None:
    pool = _sections()

    packet = context.project("challenger", pool, max_packet_bytes=100_000)

    dropped = next(record for record in packet.sections if record.name == context.DIFF)
    assert dropped.included is False
    assert dropped.mode == "excluded"
    assert "not projected for role challenger" in dropped.reason
    assert dropped.source_bytes == len("diff --git a/x b/x")
    assert dropped.sha256 == hashlib.sha256(b"diff --git a/x b/x").hexdigest()


def test_disabling_projection_restores_the_v0_1_shape() -> None:
    pool = _sections()

    packet = context.project("challenger", pool, max_packet_bytes=100_000, enabled=False)

    assert all(record.included for record in packet.sections)


def test_an_oversized_section_is_indexed_by_sha_and_path_never_byte_truncated() -> None:
    body = "\n".join(f"line {index}" for index in range(4000))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    pool = [
        context.Section(
            name=context.CONSTITUTION, text="rules", reason="authority", required=True
        ),
        context.Section(
            name=context.DIFF,
            text=body,
            reason="what changed",
            required=True,
            path=Path("tasks/demo/artifacts/history/review-1/full.diff"),
        ),
    ]

    packet = context.project("reviewer", pool, max_packet_bytes=8_000)

    record = next(item for item in packet.sections if item.name == context.DIFF)
    assert record.mode == "indexed"
    assert record.included is True
    assert record.source_bytes == len(body.encode("utf-8"))
    assert record.packet_bytes < record.source_bytes
    # The identity and the location survive, so the agent can resolve the full artifact.
    assert digest in packet.text
    assert "tasks/demo/artifacts/history/review-1/full.diff" in packet.text
    assert "lines omitted" in packet.text
    # Head and tail are whole lines: nothing was cut mid-line to hit a byte count.
    assert "line 0" in packet.text
    assert "line 3999" in packet.text
    for line in packet.text.splitlines():
        assert not line.startswith("line ") or line in body.splitlines()


def test_a_required_section_is_never_dropped_to_meet_the_budget() -> None:
    pool = [
        context.Section(
            name=context.CONSTITUTION,
            text="rules " * 5000,
            reason="authority",
            required=True,
        ),
        context.Section(
            name=context.ARC_STATE, text="state " * 5000, reason="where we are", required=False
        ),
    ]

    packet = context.project("planner", pool, max_packet_bytes=500)

    records = {record.name: record for record in packet.sections}
    assert records[context.CONSTITUTION].included is True
    assert records[context.ARC_STATE].included is False


def test_a_section_over_its_own_ceiling_is_indexed_even_inside_the_packet_budget() -> None:
    pool = [
        context.Section(
            name=context.DIFF,
            text="\n".join(f"+{index}" for index in range(2000)),
            reason="what changed",
            required=True,
            max_bytes=1_000,
        )
    ]

    packet = context.project("reviewer", pool, max_packet_bytes=10_000_000)

    assert next(item for item in packet.sections if item.name == context.DIFF).mode == "indexed"
