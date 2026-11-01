from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from maru.core.governance import BlockerClass, FindingClass


def utc_now() -> datetime:
    return datetime.now(UTC)


class ArcState(StrEnum):
    PLANNING = "PLANNING"
    PLAN_REVIEW = "PLAN_REVIEW"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    CODE_REVIEW = "CODE_REVIEW"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    # MERGED is the terminal success state, kept under its v0.1 name so existing databases,
    # traces and tooling keep their meaning. REJECTED is its counterpart: a human refused the
    # result, which is not the same thing as the relay failing.
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


TERMINAL_STATES = frozenset({ArcState.MERGED, ArcState.REJECTED, ArcState.FAILED})


class TaskState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class GateStatus(StrEnum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Arc(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    state: ArcState = ArcState.PLANNING
    current_agent: str | None = None
    next_step: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("goal")
    @classmethod
    def goal_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal cannot be blank")
        return value.strip()


class Task(BaseModel):
    id: str
    arc_id: str
    description: str
    state: TaskState = TaskState.PENDING
    depends_on: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    path: Path
    kind: str


class Run(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    arc_id: str
    role: str
    backend: str
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    exit_code: int | None = None


class HumanGate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    arc_id: str
    reason: str
    status: GateStatus = GateStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class AgentRequest(BaseModel):
    role: str
    permission: Literal["read-only", "workspace-write"] = "read-only"
    prompt: str
    schema_path: Path | None = None
    model: str | None = None


class AgentResult(BaseModel):
    backend: str
    role: str
    exit_code: int
    stdout: str
    stderr: str
    structured_result: dict[str, Any] | None = None
    session_id: str | None = None
    # Only when the adapter actually reports them. MARU never estimates a model name or a
    # token count: an invented number that looks authoritative is worse than no number.
    model: str | None = None
    tokens: int | None = None
    started_at: datetime
    finished_at: datetime
    rendered_prompt_path: Path
    raw_log_path: Path
    stderr_path: Path


class AgentBlocker(BaseModel):
    """A typed refusal: the agent did no work, and this says why in MARU's own vocabulary.

    An agent that cannot legally or physically do the job says so *here*, never only in prose.
    The classification alone decides routing, so Core never has to read a `notes` array looking
    for the word "cannot" - which is exactly what the dogfooding run caught it failing to do.

    A blocker and completed work are mutually exclusive. When both are present the blocker wins
    and the relay stops; git, not the artifact, remains the authority on what actually changed.
    """

    classification: BlockerClass
    message: str
    # The frozen criterion or project rule this blocker is about, when there is one.
    criterion: str | None = None
    # Who holds the authority the agent lacks, e.g. "human" or ".maru/constitution.md rule 8".
    authority: str | None = None
    details: list[str] = Field(default_factory=list)


class PlanTask(BaseModel):
    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class PlanArtifact(BaseModel):
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    tasks: list[PlanTask]
    acceptance_criteria: list[str]
    risks: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list)
    # Named ids the Challenger and Reviewer are allowed to block on. Once the plan is accepted
    # this is the frozen blocking surface; a finding outside it escalates to a human instead of
    # spending another plan revision on an ever-widening review.
    blocking_surface: list[str] = Field(default_factory=list)
    # Set instead of planning when the request cannot legally or physically be planned here.
    blocker: AgentBlocker | None = None

    @property
    def frozen_surface(self) -> list[str]:
        return self.blocking_surface or self.acceptance_criteria


class PlanFinding(BaseModel):
    severity: Literal["blocking", "non-blocking"]
    evidence: str
    message: str
    # Optional so a v0.1 Challenger artifact still validates and behaves exactly as before.
    classification: FindingClass = FindingClass.BLOCKING_IN_SCOPE
    criterion: str | None = None


class PlanReviewArtifact(BaseModel):
    result: Literal["pass", "fail"]
    findings: list[PlanFinding] = Field(default_factory=list)
    recommendation: str

    @model_validator(mode="after")
    def pass_has_no_blockers(self) -> PlanReviewArtifact:
        if self.result == "pass" and any(f.severity == "blocking" for f in self.findings):
            raise ValueError("a passing plan review cannot contain blocking findings")
        return self


class ImplementationArtifact(BaseModel):
    """What the Worker did. MARU Core, not the Worker, executes the test gate."""

    changed_files: list[str]
    notes: list[str] = Field(default_factory=list)
    tests_expected: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    # Set instead of implementing when the accepted plan cannot be executed from here.
    # An empty `changed_files` with no blocker is a deliberate no-op, not a failure.
    blocker: AgentBlocker | None = None


class ReviewFinding(BaseModel):
    file: str
    location: str
    evidence: str
    message: str
    classification: FindingClass = FindingClass.BLOCKING_IN_SCOPE
    criterion: str | None = None


class ReviewArtifact(BaseModel):
    result: Literal["pass", "fail"]
    blocking: list[ReviewFinding] = Field(default_factory=list)
    non_blocking: list[ReviewFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def pass_has_no_blockers(self) -> ReviewArtifact:
        if any(
            finding.classification in {FindingClass.NON_BLOCKING, FindingClass.OUT_OF_SCOPE}
            for finding in self.blocking
        ):
            raise ValueError("non-blocking or out-of-scope findings cannot be in the blocking list")
        if self.result == "pass" and self.blocking:
            raise ValueError("a passing code review cannot contain blocking findings")
        return self
