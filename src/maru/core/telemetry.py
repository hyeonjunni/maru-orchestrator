"""Per-invocation cost telemetry, derived from the event log rather than a second ledger.

Token counts are recorded only when an adapter actually reports them. MARU never invents them:
an estimated token number that looks authoritative is worse than an honest byte count.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maru.events.models import MaruEvent


class RoleCost(BaseModel):
    invocations: int = 0
    prompt_bytes: int = 0
    context_bytes: int = 0
    duration_s: float = 0.0
    fallbacks: int = 0
    tokens: int | None = None


class ArcCost(BaseModel):
    roles: dict[str, RoleCost] = Field(default_factory=dict)
    failures: dict[str, int] = Field(default_factory=dict)

    @property
    def invocations(self) -> int:
        return sum(role.invocations for role in self.roles.values())

    @property
    def prompt_bytes(self) -> int:
        return sum(role.prompt_bytes for role in self.roles.values())

    @property
    def repeated_review_bytes(self) -> int:
        """Bytes spent re-sending review context after the first review.

        This is the number the dogfooding run could not see: with a cumulative diff it grows
        like `artifact_size x iterations`, and it is what incremental review is meant to flatten.
        """
        reviewer = self.roles.get("reviewer")
        if reviewer is None or reviewer.invocations < 2:
            return 0
        return reviewer.prompt_bytes - reviewer.prompt_bytes // reviewer.invocations


def summarize(events: list[MaruEvent]) -> ArcCost:
    cost = ArcCost()
    for event in events:
        payload = event.payload
        if event.type == "AGENT_COMPLETED":
            role = cost.roles.setdefault(str(payload.get("role", "unknown")), RoleCost())
            role.invocations += 1
            role.prompt_bytes += int(payload.get("prompt_bytes", 0) or 0)
            role.context_bytes += int(payload.get("context_bytes", 0) or 0)
            role.duration_s += float(payload.get("duration_s", 0.0) or 0.0)
            role.fallbacks += 1 if payload.get("fallback_used") else 0
            tokens = payload.get("tokens")
            if tokens is not None:
                role.tokens = (role.tokens or 0) + int(tokens)
        elif event.type == "STAGE_FAILED":
            failure = str(payload.get("failure", "UNKNOWN"))
            cost.failures[failure] = cost.failures.get(failure, 0) + 1
    return cost


def render(cost: ArcCost) -> str:
    lines = [
        f"Role invocations: {cost.invocations}",
        f"Total prompt bytes: {cost.prompt_bytes} ({cost.prompt_bytes / 1024:.1f} KiB)",
    ]
    for role, entry in cost.roles.items():
        detail = (
            f"  {role}: {entry.invocations} calls, {entry.prompt_bytes / 1024:.1f} KiB prompt"
            f", {entry.duration_s:.1f}s"
        )
        if entry.fallbacks:
            detail += f", {entry.fallbacks} on a fallback provider"
        if entry.tokens is not None:
            detail += f", {entry.tokens} tokens"
        lines.append(detail)
    lines.append(
        f"Repeated review-loop bytes (estimate): {cost.repeated_review_bytes / 1024:.1f} KiB"
    )
    if cost.failures:
        lines.append("Failures: " + ", ".join(f"{k}={v}" for k, v in sorted(cost.failures.items())))
    return "\n".join(lines)
