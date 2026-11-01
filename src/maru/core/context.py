"""Role-specific context projection with a deterministic budget.

MARU v0.1 rendered one required-input inventory and one context blob into every role, so the
same durable record was replicated four times per relay and re-sent on every fix loop. The
durable record is unchanged: everything still lives on disk, addressable by path and SHA-256.
What changes here is the *projection* - each role receives only the sections its task needs,
and every section a packet drops or indexes says so in an audit manifest.

Over budget never means cutting arbitrary bytes. A section that does not fit is replaced by a
deterministic index: its head, its tail, its size, its SHA-256 and its path on disk. The agent
can always resolve the full artifact locally; it is never asked to remember it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

INDEX_HEAD_LINES = 40
INDEX_TAIL_LINES = 20


# Section names, so the projection table and the relay cannot drift apart.
CONSTITUTION = "constitution"
REQUEST = "request"
REQUIRED_INPUTS = "required-inputs"
ARC_STATE = "arc-state"
UNRESOLVED_BLOCKERS = "unresolved-blockers"
REVISION_CONTEXT = "revision-context"
PROPOSED_PLAN = "proposed-plan"
BLOCKING_SURFACE = "blocking-surface"
ACCEPTED_PLAN = "accepted-plan"
WRITABLE_SCOPE = "writable-scope"
TEST_CONTRACT = "test-contract"
FIX_CONTEXT = "fix-context"
IMPLEMENTATION_REPORT = "implementation-report"
TEST_OUTPUT = "test-output"
DIFF = "diff"
PRIOR_FINDINGS = "prior-findings"

# What each role's task actually requires. The Challenger never needs the implementation diff;
# the Reviewer never needs the historical planning handoffs. Everything omitted here still
# exists on disk and is named in the packet manifest with the reason it was left out.
ROLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "planner": (
        CONSTITUTION,
        REQUEST,
        REQUIRED_INPUTS,
        ARC_STATE,
        UNRESOLVED_BLOCKERS,
        REVISION_CONTEXT,
    ),
    "challenger": (
        CONSTITUTION,
        REQUEST,
        PROPOSED_PLAN,
        BLOCKING_SURFACE,
        REQUIRED_INPUTS,
        PRIOR_FINDINGS,
    ),
    "worker": (
        CONSTITUTION,
        ACCEPTED_PLAN,
        REQUIRED_INPUTS,
        WRITABLE_SCOPE,
        TEST_CONTRACT,
        FIX_CONTEXT,
    ),
    # The Reviewer keeps the input inventory: it is a few lines, and it is the only way to see
    # that the implementation cited the snapshot rather than some sibling checkout.
    "reviewer": (
        CONSTITUTION,
        ACCEPTED_PLAN,
        REQUIRED_INPUTS,
        IMPLEMENTATION_REPORT,
        TEST_OUTPUT,
        DIFF,
        PRIOR_FINDINGS,
    ),
}


class Section(BaseModel):
    """One candidate block of context, and why this role is being given it."""

    name: str
    text: str
    reason: str
    required: bool = False
    path: Path | None = None
    # A per-section ceiling, used for the diff: a huge artifact is indexed even when the packet
    # as a whole would still fit under its budget.
    max_bytes: int | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def bytes(self) -> int:
        return len(self.text.encode("utf-8"))


class SectionRecord(BaseModel):
    """The audit row for one section: what happened to it, and where the full copy lives."""

    name: str
    reason: str
    mode: str  # full | indexed | excluded
    included: bool
    source_bytes: int
    packet_bytes: int
    sha256: str
    path: str | None = None


class ContextPacket(BaseModel):
    role: str
    text: str
    sections: list[SectionRecord] = Field(default_factory=list)

    @property
    def bytes(self) -> int:
        return len(self.text.encode("utf-8"))


def _index(section: Section) -> str:
    """A stable stand-in for a section too large to send: head, tail, identity, location."""
    lines = section.text.splitlines()
    location = section.path.as_posix() if section.path is not None else "(in-memory)"
    header = [
        f"[INDEXED] {section.name} was too large for this context budget and is summarized.",
        f"Full artifact: {location}",
        f"sha256={section.sha256} bytes={section.bytes} lines={len(lines)}",
        "Read the full artifact from that path if a finding depends on the omitted part.",
        "",
    ]
    if len(lines) <= INDEX_HEAD_LINES + INDEX_TAIL_LINES:
        return "\n".join(header + lines)
    omitted = len(lines) - INDEX_HEAD_LINES - INDEX_TAIL_LINES
    return "\n".join(
        header
        + lines[:INDEX_HEAD_LINES]
        + ["", f"... {omitted} lines omitted; read {location} for them ...", ""]
        + lines[-INDEX_TAIL_LINES:]
    )


def build_context_packet(
    role: str, sections: list[Section], *, max_packet_bytes: int
) -> ContextPacket:
    """Render ``sections`` for ``role`` within budget, recording what each section became.

    Required sections are never dropped - a projection that silently discarded required
    authority would be worse than an expensive one. They are indexed if they do not fit, and an
    optional section is excluded only after every larger optional one already was.
    """
    rendered: dict[str, str] = {}
    records: dict[str, SectionRecord] = {}
    for section in sections:
        rendered[section.name] = section.text
        records[section.name] = SectionRecord(
            name=section.name,
            reason=section.reason,
            mode="full",
            included=True,
            source_bytes=section.bytes,
            packet_bytes=section.bytes,
            sha256=section.sha256,
            path=section.path.as_posix() if section.path is not None else None,
        )

    def total() -> int:
        return sum(len(_block(name, text).encode("utf-8")) for name, text in rendered.items())

    def index_section(section: Section) -> None:
        indexed = _index(section)
        if len(indexed) >= section.bytes:
            return
        rendered[section.name] = indexed
        records[section.name] = records[section.name].model_copy(
            update={"mode": "indexed", "packet_bytes": len(indexed.encode("utf-8"))}
        )

    for section in sections:
        if section.max_bytes is not None and section.bytes > section.max_bytes:
            index_section(section)

    # Largest first: one oversized artifact is the reason a packet blows its budget, and
    # indexing it recovers far more than trimming several small ones.
    by_size = sorted(sections, key=lambda item: item.bytes, reverse=True)
    for section in by_size:
        if total() <= max_packet_bytes:
            break
        if records[section.name].mode == "full":
            index_section(section)
    for section in by_size:
        if total() <= max_packet_bytes:
            break
        if section.required:
            continue
        rendered.pop(section.name, None)
        records[section.name] = records[section.name].model_copy(
            update={"mode": "excluded", "included": False, "packet_bytes": 0}
        )
    text = "\n".join(_block(name, rendered[name]) for name in rendered)
    return ContextPacket(
        role=role, text=text, sections=[records[section.name] for section in sections]
    )


def project(
    role: str,
    pool: list[Section],
    *,
    max_packet_bytes: int,
    enabled: bool = True,
) -> ContextPacket:
    """Project the durable record onto one role, then fit it to the budget.

    ``pool`` is everything the relay currently knows. Sections this role's task does not need
    are recorded as excluded with that reason, so the packet stays auditable: a reader can see
    what existed and why it was not sent, rather than guessing what the agent was shown.
    """
    wanted = ROLE_SECTIONS.get(role)
    if not enabled or wanted is None:
        return build_context_packet(role, pool, max_packet_bytes=max_packet_bytes)
    kept = [section for section in pool if section.name in wanted]
    packet = build_context_packet(role, kept, max_packet_bytes=max_packet_bytes)
    dropped = [
        SectionRecord(
            name=section.name,
            reason=f"not projected for role {role}: {section.reason}",
            mode="excluded",
            included=False,
            source_bytes=section.bytes,
            packet_bytes=0,
            sha256=section.sha256,
            path=section.path.as_posix() if section.path is not None else None,
        )
        for section in pool
        if section.name not in wanted
    ]
    return packet.model_copy(update={"sections": packet.sections + dropped})


def _block(name: str, text: str) -> str:
    return f"## {name}\n\n{text}\n"


def summarize_packets(packets: dict[str, int]) -> str:
    """`Planner context: 24 KB` lines for the human summary and `maru status`."""
    return "\n".join(
        f"{role.capitalize()} context: {size / 1024:.1f} KiB" for role, size in packets.items()
    )
