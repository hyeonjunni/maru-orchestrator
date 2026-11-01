from __future__ import annotations

from maru.core import telemetry
from maru.events.models import MaruEvent


def _completed(role: str, **payload) -> MaruEvent:
    return MaruEvent(
        arc_id="arc-1",
        source=role,
        type="AGENT_COMPLETED",
        payload={"role": role, "prompt_bytes": 1000, "duration_s": 1.5} | payload,
    )


def test_summarize_counts_invocations_and_bytes_per_role() -> None:
    events = [
        _completed("planner"),
        _completed("reviewer", prompt_bytes=100_000),
        _completed("reviewer", prompt_bytes=20_000, fallback_used=True),
        MaruEvent(
            arc_id="arc-1",
            source="core",
            type="STAGE_FAILED",
            payload={"role": "reviewer", "failure": "RESOURCE_EXHAUSTED"},
        ),
    ]

    cost = telemetry.summarize(events)

    assert cost.invocations == 3
    assert cost.prompt_bytes == 121_000
    assert cost.roles["reviewer"].invocations == 2
    assert cost.roles["reviewer"].fallbacks == 1
    assert cost.failures == {"RESOURCE_EXHAUSTED": 1}
    # Everything after the first review is repeated review context, which is the number the
    # dogfooding run could not see.
    assert cost.repeated_review_bytes == 60_000


def test_tokens_are_only_reported_when_an_adapter_actually_provided_them() -> None:
    assert telemetry.summarize([_completed("planner")]).roles["planner"].tokens is None
    assert telemetry.summarize([_completed("planner", tokens=42)]).roles["planner"].tokens == 42


def test_render_is_readable_and_names_the_repeated_review_cost() -> None:
    text = telemetry.render(telemetry.summarize([_completed("planner")]))

    assert "Role invocations: 1" in text
    assert "planner: 1 calls" in text
    assert "Repeated review-loop bytes" in text
