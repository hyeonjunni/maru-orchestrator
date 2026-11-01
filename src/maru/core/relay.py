from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Never, cast

from pydantic import BaseModel, ValidationError

from maru.agents.adapters.base import find_executable, run_process
from maru.agents.adapters.claude import ClaudeAdapter
from maru.agents.adapters.codex import CodexAdapter
from maru.agents.failures import FailureKind, classify
from maru.agents.protocol import AgentAdapter
from maru.core import context, inputs, telemetry
from maru.core.assets import AssetError, resolve_prompt, resolve_schema
from maru.core.config import MaruConfig, load_config, maru_owned
from maru.core.governance import (
    BlockerClass,
    EvidenceLevel,
    FindingClass,
    blocker_payload,
    escalation_for,
    evidence_level,
    from_failure,
    policy_for,
)
from maru.core.models import (
    TERMINAL_STATES,
    AgentBlocker,
    AgentRequest,
    AgentResult,
    Arc,
    ArcState,
    ArtifactRef,
    HumanGate,
    ImplementationArtifact,
    PlanArtifact,
    PlanReviewArtifact,
    ReviewArtifact,
)
from maru.core.testgate import DeterministicGateError, missing_executables, run_test_gate
from maru.events.models import MaruEvent
from maru.guard.policy import protected_scope_text, review_worker_changes
from maru.storage.sqlite import SqliteStore

AdapterFactory = Callable[[str], AgentAdapter]
TestRunner = Callable[[Path], tuple[bool, str]]

_ARTIFACTS: dict[str, tuple[str, type[BaseModel]]] = {
    "planner": ("plan.json", PlanArtifact),
    "challenger": ("plan-review.json", PlanReviewArtifact),
    "worker": ("implementation.json", ImplementationArtifact),
    "reviewer": ("code-review.json", ReviewArtifact),
}

BLOCKED_INPUT_CLOSURE = "BLOCKED_INPUT_CLOSURE"
BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"


class RelayStopped(RuntimeError):
    pass


@contextmanager
def project_lock(root: Path) -> Iterator[None]:
    """Exclude competing relay processes; OS ownership is released even after a crash."""
    root = root.resolve()
    config = load_config(root)
    lock_path = root / config.paths.state_dir / "relay.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RelayStopped("Another relay is already running in this project") from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise RelayStopped("Another relay is already running in this project") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_adapter_factory(backend: str) -> AgentAdapter:
    if backend == "claude":
        return ClaudeAdapter()
    if backend == "codex":
        return CodexAdapter()
    raise RelayStopped(f"Unsupported backend: {backend}")


def task_dir_for(root: Path, config: MaruConfig, slug: str) -> Path:
    """Validate ``slug`` and return its task directory, which never escapes the tasks root."""
    tasks_root = (root / config.paths.tasks).resolve()
    task_dir = (tasks_root / slug).resolve()
    if (
        not slug.strip()
        or any(separator in slug for separator in ("/", "\\"))
        or Path(slug).name != slug
        or task_dir.parent != tasks_root
    ):
        raise RelayStopped(f"Invalid task slug: {slug}")
    return task_dir


def start_run(
    root: Path, slug: str, *, prompt_file: Path | None = None, goal: str | None = None
) -> Path:
    with project_lock(root):
        return _start_run(root, slug, prompt_file=prompt_file, goal=goal)


def _start_run(
    root: Path, slug: str, *, prompt_file: Path | None = None, goal: str | None = None
) -> Path:
    """Public entrypoint helper: record the request for ``slug`` before the relay runs.

    Exactly one Arc exists per slug, so ``maru run`` snapshots the request into the task
    directory rather than creating a second, unrelated Arc from the prompt file.
    """
    root = root.resolve()
    config = load_config(root)
    task_dir = task_dir_for(root, config, slug)
    if (prompt_file is None) == (goal is None):
        raise RelayStopped("Provide exactly one of a goal or --prompt-file")
    if prompt_file is not None:
        try:
            text = prompt_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise RelayStopped(f"Cannot read request file {prompt_file}: {error}") from error
    else:
        assert goal is not None
        text = f"# What I want\n\n{goal}\n"
    if not text.strip():
        raise RelayStopped("The request is blank")
    request_path = task_dir / "request.md"
    if request_path.exists():
        if request_path.read_text(encoding="utf-8") != text:
            raise RelayStopped(f"Arc {slug} has a different request; use a new slug")
        return task_dir
    task_dir.mkdir(parents=True, exist_ok=True)
    request_path.write_text(text, encoding="utf-8")
    return task_dir


def run_relay(
    root: Path,
    slug: str,
    *,
    adapter_factory: AdapterFactory | None = None,
    test_runner: TestRunner | None = None,
    timeout_s: float | None = 1800,
    test_timeout_s: float | None = 300,
) -> Path:
    with project_lock(root):
        return _run_relay(
            root,
            slug,
            adapter_factory=adapter_factory,
            test_runner=test_runner,
            timeout_s=timeout_s,
            test_timeout_s=test_timeout_s,
        )


def _run_relay(  # noqa: C901 - one relay, one readable sequence; splitting it hides the order
    root: Path,
    slug: str,
    *,
    adapter_factory: AdapterFactory | None = None,
    test_runner: TestRunner | None = None,
    timeout_s: float | None = 1800,
    test_timeout_s: float | None = 300,
) -> Path:
    # Resolved here rather than as a default argument so the public entrypoint and the tests
    # share one factory lookup.
    adapter_factory = adapter_factory or default_adapter_factory
    if timeout_s is not None and timeout_s <= 0:
        raise RelayStopped("Agent timeout must be positive")
    if test_timeout_s is not None and test_timeout_s <= 0:
        raise RelayStopped("Test timeout must be positive")
    root = root.resolve()
    config = load_config(root)
    owned = maru_owned(config)
    task_dir = task_dir_for(root, config, slug)
    request_path = task_dir / "request.md"
    if not request_path.is_file():
        raise RelayStopped(f"Request not found: {request_path}")
    rendered_dir = task_dir / "rendered"
    artifacts_dir = task_dir / "artifacts"
    history_dir = artifacts_dir / "history"
    logs_dir = task_dir / "logs"
    for directory in (rendered_dir, artifacts_dir, history_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    request_text = request_path.read_text(encoding="utf-8")

    store = SqliteStore(root / config.paths.state_db)
    store.initialize()
    arc = _restore_or_create_arc(store, slug, _goal_from_request(request_text, slug))

    # Include rendered attempts: a failed launch may have no validated history artifact.
    calls = {
        role: max(
            (
                int(path.stem.rsplit("-", 1)[1])
                for path in rendered_dir.glob(f"{role}-*.md")
                if path.stem.rsplit("-", 1)[1].isdigit()
            ),
            default=0,
        )
        for role in _ARTIFACTS
    }
    review_offset = max(
        (
            int(path.name.removeprefix("review-"))
            for path in history_dir.glob("review-*")
            if path.name.removeprefix("review-").isdigit()
        ),
        default=0,
    )
    providers: dict[str, str] = {}
    prompt_bytes: dict[str, int] = {}

    def record(source: str, event_type: str, payload: dict[str, Any], *artifacts: Path) -> None:
        store.append_event(
            MaruEvent(
                arc_id=arc.id,
                source=source,
                type=event_type,
                payload=payload,
                artifact_refs=[_artifact_ref(root, path) for path in artifacts],
            )
        )

    def advance(state: ArcState, current_agent: str, next_step: str) -> None:
        store.transition_arc(
            arc.id, state, source="core", current_agent=current_agent, next_step=next_step
        )

    def stop(
        reason: str,
        blocker: BlockerClass = BlockerClass.OTHER,
        *,
        role: str = "core",
        detail: dict[str, Any] | None = None,
        artifacts: tuple[Path, ...] = (),
    ) -> Never:
        """Pause the Arc with a typed blocker, and raise it to a human when it owns the fix.

        ``role`` is who raised it - "core" for a blocker MARU detected itself, or the agent role
        when the Planner or Worker returned a typed blocker instead of doing the work. Nothing
        here is inferred from prose.
        """
        policy = policy_for(blocker)
        changed_paths: list[str] | None
        try:
            changed_paths = sorted(path for path in git_changed_paths(root) if not owned(path))
        except OSError:
            changed_paths = None
        work_performed = bool(changed_paths) if changed_paths is not None else None
        level = (
            EvidenceLevel.BLOCKED_WORK_UNKNOWN if work_performed is None
            else EvidenceLevel.BLOCKED_WITH_CHANGES if work_performed
            else EvidenceLevel.BLOCKED_NO_IMPLEMENTATION
        )
        _write_summary(
            artifacts_dir,
            "Relay stopped",
            reason,
            ready=False,
            evidence=level,
            blocker=blocker,
            blocker_role=role,
            packets=prompt_bytes,
        )
        current = store.get_arc(arc.id)
        if current is not None and current.state not in TERMINAL_STATES:
            if current.state is not ArcState.PAUSED:
                store.transition_arc(
                    arc.id,
                    ArcState.PAUSED,
                    source="core",
                    current_agent="human",
                    next_step=reason,
                )
            record(
                "core",
                "BLOCKER_RAISED",
                {"role": role} | blocker_payload(blocker, reason) | (detail or {}),
                artifacts_dir / "human-summary.md",
                *artifacts,
            )
            record(
                "core",
                "EVIDENCE_ASSESSED",
                {"evidence_level": level.value, "providers": providers,
                 "work_performed": work_performed, "changed_paths": changed_paths},
            )
            if policy.requires_decision:
                # A human has to decide something here, so it belongs in `maru inbox` rather
                # than quietly consuming another Planner revision.
                gate = HumanGate(arc_id=arc.id, reason=f"{blocker.value}: {reason}")
                store.create_gate(gate)
                record(
                    "core",
                    "GATE_OPENED",
                    {
                        "gate_id": gate.id,
                        "blocker": blocker.value,
                        "role": role,
                        "owner": policy.owner,
                        "message": reason,
                        "evidence_level": level.value,
                    },
                )
            record("core", "RELAY_STOPPED", {"reason": reason, "blocker": blocker.value})
        raise RelayStopped(reason)

    # Required inputs are captured before anyone plans, so Planner, Challenger, Worker and
    # Reviewer all reason about the same in-repository snapshot.
    try:
        manifest = inputs.snapshot(
            task_dir, inputs.declarations(task_dir), root=root, git_probe=_git_probe
        )
    except (inputs.InputClosureError, OSError) as error:
        stop(f"{BLOCKED_INPUT_CLOSURE}: {error}", BlockerClass.INPUT_MISSING)
    if manifest.inputs:
        record(
            "core",
            "INPUTS_SNAPSHOTTED",
            {"inputs": [record_.model_dump(mode="json") for record_ in manifest.inputs]},
            task_dir / inputs.SNAPSHOT_DIR / inputs.MANIFEST_FILE,
        )
    input_inventory = inputs.inventory_text(manifest)
    constitution_path = root / ".maru" / "constitution.md"
    constitution = (
        constitution_path.read_text(encoding="utf-8").strip()
        if constitution_path.is_file()
        else "No project Constitution found."
    )

    def base_sections() -> list[context.Section]:
        """The durable context every stage starts from, before role projection."""
        current = store.get_arc(arc.id)
        return [
            context.Section(
                name=context.CONSTITUTION,
                text=constitution,
                reason="frozen project authority",
                required=True,
                path=constitution_path if constitution_path.is_file() else None,
            ),
            context.Section(
                name=context.REQUEST,
                text=request_text,
                reason="what the human asked for",
                required=True,
                path=request_path,
            ),
            context.Section(
                name=context.REQUIRED_INPUTS,
                text=input_inventory,
                reason="immutable input snapshots this task may cite",
                required=True,
                path=task_dir / inputs.SNAPSHOT_DIR / inputs.MANIFEST_FILE
                if manifest.inputs
                else None,
            ),
            context.Section(
                name=context.ARC_STATE,
                text=(
                    f"Arc: {arc.id}\nState: {current.state.value if current else arc.state.value}\n"
                    f"Plan revisions allowed: {config.limits.plan_revisions}\n"
                    f"Review fix loops allowed: {config.limits.review_fix_loops}"
                ),
                reason="where this Arc currently stands",
            ),
        ]

    def stage(role: str, sections: list[context.Section]) -> BaseModel:
        """Project, render, run (with provider fallback), validate, persist and record."""
        calls[role] = calls.get(role, 0) + 1
        attempt = calls[role]
        settings = config.agents.get(role)
        if settings is None:
            stop(f"Missing agent configuration for role: {role}", BlockerClass.CAPABILITY_MISSING)
        packet = context.project(
            role,
            sections,
            max_packet_bytes=config.context.max_packet_bytes,
            enabled=config.context.role_projection,
        )
        stem = f"{role}-{attempt:03d}"
        try:
            prompt = f"{resolve_prompt(root, role).text.strip()}\n\n{packet.text}"
            schema_text = resolve_schema(root, role).text
        except AssetError as error:
            stop(f"{role} could not run: {error}", BlockerClass.CAPABILITY_MISSING)
        # Immutable per invocation, plus a stable latest pointer for humans and tooling.
        (rendered_dir / f"{stem}.md").write_text(prompt, encoding="utf-8")
        (rendered_dir / f"{role}.md").write_text(prompt, encoding="utf-8")
        (rendered_dir / f"{stem}.context.json").write_text(
            packet.model_dump_json(indent=2, exclude={"text"}), encoding="utf-8"
        )
        schema_path = rendered_dir / f"{stem}.schema.json"
        schema_path.write_text(schema_text, encoding="utf-8")
        size = len(prompt.encode("utf-8"))
        prompt_bytes[role] = prompt_bytes.get(role, 0) + size
        record(
            "core",
            "CONTEXT_PROJECTED",
            {
                "role": role,
                "attempt": attempt,
                "prompt_bytes": size,
                "packet_bytes": packet.bytes,
                "sections": [item.model_dump(mode="json") for item in packet.sections],
            },
            rendered_dir / f"{stem}.context.json",
        )

        backends = [settings.backend]
        if config.provider_policy.allow_fallback:
            backends += [name for name in settings.fallback if name != settings.backend]
        result: AgentResult | None = None
        used_backend = settings.backend
        fallback_used = False
        for index, backend in enumerate(backends):
            last = index == len(backends) - 1
            blocker: BlockerClass
            detail = ""
            try:
                candidate = adapter_factory(backend).run(
                    AgentRequest(
                        role=role,
                        permission=settings.permission,
                        prompt=prompt,
                        schema_path=schema_path,
                    ),
                    cwd=root,
                    timeout_s=timeout_s,
                )
            except (OSError, ValueError, RelayStopped) as error:
                blocker, detail = BlockerClass.CAPABILITY_MISSING, f"LAUNCH: {error}"
                record(
                    "core",
                    "STAGE_FAILED",
                    {"role": role, "backend": backend, "attempt": attempt, "failure": "LAUNCH"}
                    | blocker_payload(blocker, detail),
                )
                if last:
                    stop(f"{role} could not run: {error}", blocker)
            else:
                _write_result_log(
                    logs_dir, role, attempt, backend, candidate.model_dump(mode="json")
                )
                if candidate.exit_code == 0:
                    result, used_backend = candidate, backend
                    break
                kind, retry_after = classify(
                    candidate.exit_code, candidate.stdout, candidate.stderr
                )
                blocker = from_failure(kind)
                detail = f"{kind.value} (exit {candidate.exit_code})" + (
                    f" (retry after {retry_after})" if retry_after else ""
                )
                record(
                    "core",
                    "STAGE_FAILED",
                    {
                        "role": role,
                        "backend": backend,
                        "attempt": attempt,
                        "failure": kind.value,
                        "exit_code": candidate.exit_code,
                        "retry_after": retry_after,
                        "raw_log": str(candidate.raw_log_path),
                    }
                    | blocker_payload(blocker, detail),
                    logs_dir / f"{role}-{attempt}-{backend}.json",
                )
                # Only an exhausted provider is worth handing to a different provider. A schema
                # or process failure would fail the same way twice and hide the real cause.
                if last or blocker is not BlockerClass.RESOURCE_EXHAUSTED:
                    stop(f"{role} failed: {detail}", blocker)
            record(
                "core",
                "PROVIDER_FALLBACK",
                {
                    "role": role,
                    "from": backend,
                    "to": backends[index + 1],
                    "reason": detail,
                    "evidence_note": "a fallback provider is not an independent provider",
                },
            )
            fallback_used = True
        assert result is not None
        if result.structured_result is None:
            record(
                "core",
                "STAGE_FAILED",
                {"role": role, "backend": used_backend, "failure": FailureKind.SCHEMA.value},
            )
            stop(
                f"{role} failed: {FailureKind.SCHEMA.value} (no structured result)",
                BlockerClass.RULE_INCOMPLETE,
            )
        filename, model_type = _ARTIFACTS[role]
        try:
            artifact = model_type.model_validate(result.structured_result)
        except ValidationError as error:
            record(
                "core",
                "STAGE_FAILED",
                {"role": role, "backend": used_backend, "failure": FailureKind.SCHEMA.value},
            )
            stop(f"Invalid {role} artifact: {error}", BlockerClass.RULE_INCOMPLETE)
        payload = artifact.model_dump_json(indent=2)
        history_path = history_dir / role / f"{attempt:03d}.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(payload, encoding="utf-8")
        artifact_path = artifacts_dir / filename
        artifact_path.write_text(payload, encoding="utf-8")
        providers[role] = used_backend
        telemetry_payload: dict[str, Any] = (
            {"tokens": result.tokens} if result.tokens is not None else {}
        )
        record(
            role,
            "AGENT_COMPLETED",
            telemetry_payload
            | {
                "role": role,
                "backend": used_backend,
                "configured_backend": settings.backend,
                "fallback_used": fallback_used,
                "attempt": attempt,
                "session_id": result.session_id,
                "model": result.model,
                "prompt_bytes": size,
                "context_bytes": packet.bytes,
                "duration_s": (result.finished_at - result.started_at).total_seconds(),
                "history_path": history_path.relative_to(root).as_posix()
                if history_path.is_relative_to(root)
                else str(history_path),
            },
            artifact_path,
            history_path,
        )
        return artifact

    plan: PlanArtifact | None = None
    plan_review: PlanReviewArtifact | None = None
    revision_sections: list[context.Section] = []
    for revision in range(config.limits.plan_revisions + 1):
        plan = cast(PlanArtifact, stage("planner", base_sections() + revision_sections))
        if plan.blocker is not None:
            # The Planner refused, in the governance vocabulary rather than in prose. Only a
            # plan-quality blocker is something a Planner revision can legally fix; anything
            # else belongs to a human now, and burning a revision on it just hides it.
            planner_blocker = plan.blocker
            planner_class = planner_blocker.classification
            planner_history = history_dir / "planner" / f"{calls['planner']:03d}.json"
            if (
                not policy_for(planner_class).fixable_by_revision
                or revision == config.limits.plan_revisions
            ):
                stop(
                    f"Planner raised a blocker: {planner_blocker.message}",
                    planner_class,
                    role="planner",
                    detail=_blocker_detail(planner_blocker),
                    artifacts=(planner_history,),
                )
            record(
                "core",
                "BLOCKER_RAISED",
                {"role": "planner", "routed_to": "planner-revision"}
                | blocker_payload(planner_class, planner_blocker.message)
                | _blocker_detail(planner_blocker),
                planner_history,
            )
            revision_sections = _blocker_revision_sections(planner_blocker)
            continue
        advance(ArcState.PLAN_REVIEW, "challenger", "Challenger reviews the plan")
        surface = _surface_text(plan)
        plan_review = cast(
            PlanReviewArtifact,
            stage(
                "challenger",
                base_sections()
                + [
                    context.Section(
                        name=context.PROPOSED_PLAN,
                        text=plan.model_dump_json(indent=2),
                        reason="the plan under review",
                        required=True,
                        path=artifacts_dir / "plan.json",
                    ),
                    context.Section(
                        name=context.BLOCKING_SURFACE,
                        text=surface,
                        reason="the only criteria a blocking finding may cite",
                        required=True,
                    ),
                ]
                + (
                    [
                        context.Section(
                            name=context.PRIOR_FINDINGS,
                            text=plan_review.model_dump_json(indent=2),
                            reason="findings this revision was meant to answer",
                        )
                    ]
                    if plan_review is not None
                    else []
                ),
            ),
        )
        record(
            "core",
            "BLOCKING_SURFACE_FROZEN",
            {"revision": revision + 1, "criteria": plan.frozen_surface},
        )
        if plan_review.result == "pass":
            break
        blocking = [finding for finding in plan_review.findings if finding.severity == "blocking"]
        for finding in blocking:
            escalated = escalation_for(finding.classification)
            if escalated is not None:
                # Outside the Planner's authority: revising the plan cannot legally fix it.
                stop(f"{finding.classification.value}: {finding.message}", escalated)
        plan_fixable = [
            finding
            for finding in blocking
            if finding.classification is FindingClass.BLOCKING_IN_SCOPE
        ]
        if not plan_fixable:
            stop(
                "Challenger failed the plan without a blocking in-scope finding: "
                f"{plan_review.recommendation}",
                BlockerClass.RULE_AMBIGUOUS,
            )
        if revision == config.limits.plan_revisions:
            stop("Plan revision limit exceeded", BlockerClass.RULE_INCOMPLETE)
        advance(ArcState.PLANNING, "planner", "Planner revises the plan")
        revision_sections = [
            context.Section(
                name=context.REVISION_CONTEXT,
                text=(
                    "Revise the previous plan using this challenger review. Fix only the named "
                    "blocking findings.\n"
                    f"Previous plan:\n{plan.model_dump_json(indent=2)}\n"
                    "Challenger review:\n"
                    f"{plan_review.model_dump_json(indent=2)}"
                ),
                reason="what the previous revision got wrong",
                required=True,
            ),
            context.Section(
                name=context.UNRESOLVED_BLOCKERS,
                text="\n".join(
                    f"- [{finding.classification.value}] {finding.message}"
                    for finding in plan_fixable
                ),
                reason="blockers this revision must clear",
                required=True,
            ),
        ]

    assert plan is not None
    plan_text = plan.model_dump_json(indent=2)

    # Capability preflight: the Worker never starts on a plan this machine cannot execute.
    closure_problems = inputs.verify_closure(root, manifest)
    if closure_problems:
        record(
            "core",
            "PREFLIGHT_FAILED",
            {"reason": BLOCKED_INPUT_CLOSURE, "problems": closure_problems},
        )
        stop(
            f"{BLOCKED_INPUT_CLOSURE}: " + "; ".join(closure_problems), BlockerClass.INPUT_MISSING
        )
    problems = capability_problems(
        config,
        adapter_factory=adapter_factory,
        gate_is_configured=test_runner is not None,
    )
    if problems:
        record("core", "PREFLIGHT_FAILED", {"reason": BLOCKED_CAPABILITY, "problems": problems})
        stop(
            f"{BLOCKED_CAPABILITY}: " + "; ".join(problems), BlockerClass.CAPABILITY_MISSING
        )

    # MARU's own state and task bookkeeping are not the user's source: they never make the
    # baseline dirty and never belong in the review diff.
    try:
        dirty = sorted(path for path in git_changed_paths(root) if not owned(path))
        baseline_commit = _git(root, "rev-parse", "HEAD").strip()
    except OSError as error:
        stop(f"Cannot establish the relay git baseline: {error}", BlockerClass.CAPABILITY_MISSING)
    if dirty:
        stop(
            "Relay needs a clean git working tree before the Worker starts, so the review diff "
            "can only contain relay changes. Commit, stash, or revert these paths yourself and "
            "rerun; MARU will not touch them: " + ", ".join(dirty),
            BlockerClass.CAPABILITY_MISSING,
        )
    advance(ArcState.IMPLEMENTING, "worker", "Worker implements the approved plan")
    plan_section = context.Section(
        name=context.ACCEPTED_PLAN,
        text=plan_text,
        reason="the accepted plan this Arc implements",
        required=True,
        path=artifacts_dir / "plan.json",
    )
    scope_section = context.Section(
        name=context.WRITABLE_SCOPE,
        text=protected_scope_text(),
        reason="exactly what the Worker may and may not write",
        required=True,
    )
    contract_section = context.Section(
        name=context.TEST_CONTRACT,
        text=_test_contract(config, injected=test_runner is not None),
        reason="the deterministic gate MARU Core will run",
        required=True,
    )
    fix_sections: list[context.Section] = []
    review: ReviewArtifact | None = None
    previous_tree: str | None = None
    previous_tests = ""
    tests_passed = False
    for fix in range(config.limits.review_fix_loops + 1):
        iteration = fix + 1
        evidence_iteration = review_offset + iteration
        try:
            before_worker = git_changed_paths(root)
        except OSError as error:
            stop(
                f"Cannot verify worker changes without git: {error}",
                BlockerClass.CAPABILITY_MISSING,
            )
        worker_sections = [plan_section, scope_section, contract_section]
        implementation = cast(
            ImplementationArtifact,
            stage("worker", base_sections() + worker_sections + fix_sections),
        )
        if implementation.blocker is not None:
            # The Worker could not execute the accepted plan and said so in the typed channel.
            # Nothing was implemented, so there is nothing to gate, nothing to review, and no
            # second Worker attempt that would change the answer. Stop, fail closed.
            worker_class = implementation.blocker.classification
            stop(
                f"Worker raised a blocker: {implementation.blocker.message}",
                worker_class,
                role="worker",
                detail=_blocker_detail(implementation.blocker),
                artifacts=(history_dir / "worker" / f"{calls['worker']:03d}.json",),
            )
        review_dir = history_dir / f"review-{evidence_iteration}"
        review_dir.mkdir(parents=True, exist_ok=True)
        try:
            after_worker = git_changed_paths(root)
            worker_changed = after_worker - before_worker
            diff, relay_changed = _write_diff(root, artifacts_dir, baseline_commit, owned)
            tree = _snapshot_tree(root, config, relay_changed)
        except OSError as error:
            stop(f"Cannot capture the worker diff: {error}", BlockerClass.CAPABILITY_MISSING)
        (review_dir / "full.diff").write_text(diff, encoding="utf-8")
        incremental = (
            _git(root, "diff", previous_tree, tree, "--")
            if previous_tree is not None and tree is not None
            else ""
        )
        record(
            "core",
            "DIFF_CAPTURED",
            {
                "baseline_commit": baseline_commit,
                "relay_changed_paths": relay_changed,
                "worker_changed_paths": sorted(worker_changed),
                "iteration": iteration,
                "tree": tree,
                "full_diff_bytes": len(diff.encode("utf-8")),
                "incremental_diff_bytes": len(incremental.encode("utf-8")),
            },
            review_dir / "full.diff",
        )
        violations = review_worker_changes(
            worker_changed | set(relay_changed), plan_text, writable_paths=plan.writable_paths
        )
        if violations:
            stop(
                "Worker changed files the approved plan does not cover: " + "; ".join(violations),
                BlockerClass.AUTHORITY_CONFUSION,
            )

        advance(ArcState.TESTING, "core", "MARU runs the deterministic test gate")
        try:
            if test_runner is not None:
                tests_passed, test_output = test_runner(root)
            else:
                tests_passed, test_output = run_test_gate(
                    root,
                    config.test_gate.commands,
                    logs_dir=logs_dir,
                    attempt=evidence_iteration,
                    timeout_s=test_timeout_s,
                )
        except DeterministicGateError as error:
            stop(f"{BLOCKED_CAPABILITY}: {error}", BlockerClass.CAPABILITY_MISSING)
        test_log = logs_dir / f"tests-{evidence_iteration}.log"
        test_log.write_text(test_output, encoding="utf-8")
        record("core", "TESTS_COMPLETED", {"passed": tests_passed, "attempt": iteration}, test_log)

        try:
            checked_paths = sorted(path for path in git_changed_paths(root) if not owned(path))
            checked_tree = _snapshot_tree(root, config, checked_paths)
        except OSError as error:
            stop(f"Cannot verify workspace after checks: {error}", BlockerClass.CAPABILITY_MISSING)
        if tree is None or checked_tree is None:
            stop("Cannot verify workspace identity after checks", BlockerClass.CAPABILITY_MISSING)
        if checked_tree != tree:
            stop(
                "Deterministic checks modified the workspace; reconcile changes before rerun",
                BlockerClass.AUTHORITY_CONFUSION,
            )

        advance(ArcState.CODE_REVIEW, "reviewer", "Reviewer compares the plan against the diff")
        use_incremental = (
            config.context.review_mode == "incremental" and previous_tree is not None
        )
        diff_text = (
            _incremental_context(
                root, review_dir, baseline_commit, relay_changed, incremental, iteration
            )
            if use_incremental
            else diff
        )
        if use_incremental:
            (review_dir / "incremental.diff").write_text(diff_text, encoding="utf-8")
        review = cast(
            ReviewArtifact,
            stage(
                "reviewer",
                base_sections()
                + [
                    plan_section,
                    context.Section(
                        name=context.IMPLEMENTATION_REPORT,
                        text=implementation.model_dump_json(indent=2),
                        reason="what the Worker says it did",
                        required=True,
                        path=artifacts_dir / "implementation.json",
                    ),
                    context.Section(
                        name=context.TEST_OUTPUT,
                        text=(
                            "MARU executed the deterministic tests; the Worker did not.\n"
                            f"Deterministic tests passed: {tests_passed}\n"
                            + _gate_delta(previous_tests, test_output, iteration)
                        ),
                        reason="the deterministic gate result MARU Core produced",
                        required=True,
                        path=test_log,
                    ),
                    context.Section(
                        name=context.DIFF,
                        text=diff_text,
                        reason="incremental change since the previous review"
                        if use_incremental
                        else "full relay diff since the baseline",
                        required=True,
                        path=review_dir / ("incremental.diff" if use_incremental else "full.diff"),
                        max_bytes=config.context.max_diff_bytes,
                    ),
                ]
                + (
                    [
                        context.Section(
                            name=context.PRIOR_FINDINGS,
                            text=json.dumps(
                                [finding.model_dump(mode="json") for finding in review.blocking],
                                indent=2,
                                ensure_ascii=False,
                            ),
                            reason="blocking findings from the previous review",
                            required=True,
                        )
                    ]
                    if review is not None and review.blocking
                    else []
                ),
            ),
        )
        previous_tree, previous_tests = tree, test_output
        for blocking_finding in review.blocking:
            escalated = escalation_for(blocking_finding.classification)
            if escalated is not None:
                stop(
                    f"{blocking_finding.classification.value}: {blocking_finding.message}",
                    escalated,
                )
        if review.result == "pass" and tests_passed:
            advance(ArcState.HUMAN_APPROVAL, "human", "Approve or reject the open gate")
            # git, not the Worker's own report, decides whether anything actually changed.
            work_performed = bool(relay_changed)
            level = evidence_level(
                providers=providers,
                tests_passed=tests_passed,
                require_independent_review=(
                    config.provider_policy.require_independent_review_for_verified
                ),
                work_performed=work_performed,
            )
            record(
                "core",
                "EVIDENCE_ASSESSED",
                {
                    "evidence_level": level.value,
                    "providers": providers,
                    "work_performed": work_performed,
                    "changed_paths": relay_changed,
                },
            )
            summary = _write_summary(
                artifacts_dir,
                plan.goal,
                test_output,
                ready=True,
                evidence=level,
                packets=prompt_bytes,
                cost=telemetry_text(store, arc.id),
            )
            gate = HumanGate(arc_id=arc.id, reason=f"Approve relay result for {slug}")
            store.create_gate(gate)
            record("core", "GATE_OPENED", {"gate_id": gate.id, "evidence_level": level.value})
            return summary
        if fix == config.limits.review_fix_loops:
            stop("Review fix limit exceeded", BlockerClass.RULE_INCOMPLETE)
        advance(ArcState.IMPLEMENTING, "worker", "Worker fixes the blocking findings")
        fix_sections = [
            context.Section(
                name=context.FIX_CONTEXT,
                text=(
                    "Fix the blocking review findings and failing deterministic tests. Change "
                    "nothing else.\n"
                    f"Previous implementation report:\n{implementation.model_dump_json(indent=2)}\n"
                    f"Review:\n{review.model_dump_json(indent=2)}\n"
                    f"Deterministic tests passed: {tests_passed}\n{test_output}"
                ),
                reason="the blocking findings this iteration must clear",
                required=True,
            )
        ]
    raise AssertionError("unreachable")


def telemetry_text(store: SqliteStore, arc_id: str) -> str:
    return telemetry.render(telemetry.summarize(store.list_events(arc_id)))


def capability_problems(
    config: MaruConfig,
    *,
    adapter_factory: AdapterFactory,
    gate_is_configured: bool,
) -> list[str]:
    """Can this machine actually execute the accepted plan? Capability only, never semantics.

    ``gate_is_configured`` is true when the caller injected its own deterministic runner, in
    which case ``maru.toml`` does not need to declare commands.
    """
    problems: list[str] = []
    if find_executable(_git_bin()) is None:
        problems.append(f"git is not executable: {_git_bin()}")
    if not gate_is_configured:
        if not config.test_gate.commands:
            problems.append(
                "no deterministic checks configured; add `[test_gate] commands = [[...]]` "
                "to maru.toml"
            )
        else:
            missing = missing_executables(config.test_gate.commands)
            problems += [f"test_gate command not on PATH: {name}" for name in missing]
    for role in ("worker", "reviewer"):
        settings = config.agents.get(role)
        if settings is None:
            problems.append(f"no backend configured for {role}")
            continue
        try:
            adapter_factory(settings.backend)
        except (OSError, RelayStopped) as error:
            problems.append(f"{role} backend {settings.backend} unavailable: {error}")
    return problems


def _blocker_detail(blocker: AgentBlocker) -> dict[str, Any]:
    """The agent's own words, kept beside the routing decision its classification produced."""
    return {
        "message": blocker.message,
        "criterion": blocker.criterion,
        "authority": blocker.authority,
        "details": list(blocker.details),
    }


def _blocker_revision_sections(blocker: AgentBlocker) -> list[context.Section]:
    """Hand a plan-quality blocker back to the Planner as the thing this revision must clear."""
    return [
        context.Section(
            name=context.REVISION_CONTEXT,
            text=(
                "Your previous attempt returned a blocker instead of a plan:\n"
                f"{blocker.model_dump_json(indent=2)}\n"
                "This blocker class is one a Planner is allowed to resolve by planning "
                "differently. Either produce a plan that avoids it, or return the same "
                "blocker again if it genuinely cannot be planned around."
            ),
            reason="the blocker the previous attempt raised",
            required=True,
        ),
        context.Section(
            name=context.UNRESOLVED_BLOCKERS,
            text=f"- [{blocker.classification.value}] {blocker.message}",
            reason="blockers this revision must clear",
            required=True,
        ),
    ]


def _surface_text(plan: PlanArtifact) -> str:
    lines = [
        "A blocking finding must cite one of these frozen criteria. A problem outside them is",
        "OUT_OF_SCOPE, or HUMAN_AUTHORITY_REQUIRED / CAPABILITY_REQUIRED when it needs authority",
        "or a capability the Planner cannot grant.",
        "",
    ]
    lines += [f"- {criterion}" for criterion in plan.frozen_surface] or ["- (none declared)"]
    return "\n".join(lines)


def _test_contract(config: MaruConfig, *, injected: bool) -> str:
    if injected:
        return "MARU Core runs the caller-supplied deterministic gate after you finish."
    if not config.test_gate.commands:
        return "No deterministic checks are configured."
    commands = "\n".join(f"- {' '.join(command)}" for command in config.test_gate.commands)
    return (
        "MARU Core runs these checks, in order, after you finish. You never run them yourself:\n"
        f"{commands}"
    )


def _gate_delta(previous: str, current: str, iteration: int) -> str:
    """The gate output, or just what changed in it since the previous iteration."""
    if iteration == 1 or not previous:
        return current
    if previous == current:
        return f"Unchanged since iteration {iteration - 1}:\n{current}"
    previous_lines = set(previous.splitlines())
    new_lines = [line for line in current.splitlines() if line not in previous_lines]
    return (
        f"Changed lines since iteration {iteration - 1} "
        f"({len(new_lines)} of {len(current.splitlines())}):\n" + "\n".join(new_lines)
    )


def _incremental_context(
    root: Path,
    review_dir: Path,
    baseline_commit: str,
    changed: list[str],
    incremental: str,
    iteration: int,
) -> str:
    """Review context for iteration N>1: what changed, plus where the full diff lives.

    The full cumulative diff stays on disk and is named here by path and SHA-256. The Reviewer
    is never asked to remember it, and MARU never re-sends an unchanged 100 KB artifact.
    """
    full_path = review_dir / "full.diff"
    full_text = full_path.read_text(encoding="utf-8")
    location = (
        full_path.relative_to(root).as_posix() if full_path.is_relative_to(root) else str(full_path)
    )
    header = [
        f"# Incremental review context (iteration {iteration})",
        f"# Baseline commit: {baseline_commit}",
        f"# Full relay diff: {location}",
        f"#   sha256={hashlib.sha256(full_text.encode('utf-8')).hexdigest()} "
        f"bytes={len(full_text.encode('utf-8'))}",
        f"# Changed paths ({len(changed)}):",
    ]
    header += [f"#   {path}" for path in changed] or ["#   (none)"]
    header.append(
        "# The hunks below are only what changed since the previous review. Read the full diff "
        "at the path above if a finding depends on unchanged content."
    )
    body = incremental.strip() or "(no source change since the previous review)"
    return "\n".join(header) + "\n\n" + body + "\n"


def _restore_or_create_arc(store: SqliteStore, slug: str, goal: str) -> Arc:
    """Reuse the Arc for this task slug, or start one, and re-enter PLANNING."""
    arc = store.get_arc(slug)
    if arc is None:
        arc = Arc(id=slug, goal=goal, current_agent="planner", next_step="Planner drafts the plan")
        store.create_arc(
            arc,
            event=MaruEvent(
                arc_id=arc.id, source="core", type="ARC_CREATED", payload={"goal": goal}
            ),
        )
        return arc
    if arc.state in TERMINAL_STATES:
        raise RelayStopped(f"Arc {slug} is {arc.state.value}; start the relay under a new slug")
    if store.list_open_gates(arc.id):
        raise RelayStopped(f"Arc {slug} has an open human gate; approve or reject it first")
    if arc.state is ArcState.HUMAN_APPROVAL:
        raise RelayStopped(
            f"Arc {slug} is HUMAN_APPROVAL without an open gate; reconcile its approval record"
        )
    if arc.state is not ArcState.PLANNING:
        if arc.state is not ArcState.PAUSED:
            store.transition_arc(arc.id, ArcState.PAUSED, source="core", next_step="Relay restart")
        arc = store.transition_arc(
            arc.id,
            ArcState.PLANNING,
            source="core",
            current_agent="planner",
            next_step="Planner drafts the plan",
        )
    store.append_event(
        MaruEvent(arc_id=arc.id, source="core", type="ARC_RESTORED", payload={"goal": arc.goal})
    )
    return arc


def _goal_from_request(request_text: str, slug: str) -> str:
    """First prose line of request.md, which is what a human recognizes in `maru status`."""
    for line in request_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return slug


def _artifact_ref(root: Path, path: Path) -> ArtifactRef:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        relative = path
    return ArtifactRef(path=relative, kind=path.name)


def _git_bin() -> str:
    return os.environ.get("MARU_GIT_BIN") or shutil.which("git") or "git"


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    exit_code, stdout, stderr = run_process([_git_bin(), *args], cwd=root, timeout_s=120, env=env)
    if exit_code != 0:
        raise OSError(f"git {' '.join(args)} failed: {(stderr or stdout).strip()}")
    return stdout


def _snapshot_tree(root: Path, config: MaruConfig, changed: list[str]) -> str | None:
    """Write a git tree for the current relay state, using a private index.

    ``GIT_INDEX_FILE`` points inside MARU's own state directory, so the user's staging area is
    never touched and only the relay's own changed paths enter the tree. The resulting tree ids
    are what make review iteration N able to diff against iteration N-1 exactly.
    """
    index = root / config.paths.state_dir / "diff-index"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.unlink(missing_ok=True)
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        _git(root, "read-tree", "HEAD", env=env)
        if changed:
            _git(root, "add", "-A", "--", *changed, env=env)
        return _git(root, "write-tree", env=env).strip() or None
    except OSError:
        # Incremental review is an optimization; losing it must never stop a relay.
        return None


def _git_probe(source: Path) -> tuple[str | None, str | None, bool | None]:
    """Best-effort provenance for a snapshotted input: repo root, commit and tracked flag."""
    directory = source.parent
    try:
        repo_root = _git(directory, "rev-parse", "--show-toplevel").strip() or None
        commit = _git(directory, "rev-parse", "HEAD").strip() or None
    except OSError:
        return None, None, None
    exit_code, _, _ = run_process(
        [_git_bin(), "ls-files", "--error-unmatch", str(source)], cwd=directory, timeout_s=120
    )
    return repo_root, commit, exit_code == 0


def git_changed_paths(root: Path) -> set[str]:
    """Repository-relative POSIX paths that differ from HEAD, including untracked files."""
    output = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    fields = [field for field in output.split("\0") if field]
    paths: set[str] = set()
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.add(entry[3:])
        if entry[0] in "RC" and index < len(fields):
            paths.add(fields[index])
            index += 1
    return paths


def _write_diff(
    root: Path, artifacts_dir: Path, baseline_commit: str, owned: Callable[[str], bool]
) -> tuple[str, list[str]]:
    """Persist every change this relay made since its baseline, tracked and untracked.

    This stays cumulative: it is the audit record of the whole relay. What the Reviewer is sent
    on a later iteration is the incremental diff against the previous review's tree.
    """
    changed = sorted(path for path in git_changed_paths(root) if not owned(path))
    created = [path for path in _untracked_paths(root) if not owned(path)]
    header = [
        "# Relay changes since baseline",
        f"# Baseline commit: {baseline_commit}",
        f"# Changed paths ({len(changed)}):",
    ]
    header += [f"#   {path}" for path in changed] or ["#   (none)"]
    header.append("# Tracked hunks are `git diff <baseline>`; new files follow as add-only diffs.")
    body = [_git(root, "diff", baseline_commit, "--")]
    body += [_new_file_diff(root, path) for path in created]
    diff = "\n".join(header) + "\n\n" + "".join(body)
    (artifacts_dir / "changes.diff").write_text(diff, encoding="utf-8")
    return diff, changed


def _untracked_paths(root: Path) -> list[str]:
    """New files git is not tracking, minus everything .gitignore excludes."""
    output = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(path for path in output.split("\0") if path)


def _new_file_diff(root: Path, path: str) -> str:
    """Add-only unified diff for an untracked file, which `git diff` never shows."""
    try:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return f"diff --git a/{path} b/{path}\nnew file\n# Binary or unreadable, not shown.\n"
    added = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n"
        f"+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{added}"
    )


def _write_result_log(
    logs_dir: Path, role: str, attempt: int, backend: str, data: dict[str, Any]
) -> None:
    (logs_dir / f"{role}-{attempt}-{backend}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_summary(
    artifacts_dir: Path,
    goal: str,
    tests: str,
    *,
    ready: bool,
    evidence: EvidenceLevel | None = None,
    blocker: BlockerClass | None = None,
    blocker_role: str = "core",
    packets: dict[str, int] | None = None,
    cost: str | None = None,
) -> Path:
    status = "Ready for human review" if ready else "Human intervention required"
    sections = [f"# Human Summary\n\n## Status\n\n{status}\n\n## Goal\n\n{goal}\n"]
    if evidence is not None:
        sections.append(f"## Evidence\n\n{evidence.value}\n")
    if blocker is not None:
        policy = policy_for(blocker)
        sections.append(
            f"## Blocker\n\n{blocker.value}, raised by "
            f"{'MARU Core' if blocker_role == 'core' else blocker_role.capitalize()} "
            f"(owner: {policy.owner}, "
            f"fixable by plan revision: {policy.fixable_by_revision}, "
            f"retryable: {policy.retryable})\n\n"
            + (
                "No implementation was performed for this Arc.\n"
                if evidence is EvidenceLevel.BLOCKED_NO_IMPLEMENTATION
                else "Completion is blocked; inspect workspace changes before resuming.\n"
            )
        )
    sections.append(f"## Deterministic Tests\n\n```text\n{tests}\n```\n")
    if packets:
        sections.append(
            "## Context Cost\n\n```text\n"
            + "\n".join(f"{role}: {size / 1024:.1f} KiB prompt" for role, size in packets.items())
            + "\n```\n"
        )
    if cost:
        sections.append(f"## Cost Telemetry\n\n```text\n{cost}\n```\n")
    sections.append(
        "## Gate\n\nReview the artifacts before any commit, merge, or push.\n"
        "Run `maru status`, `maru inbox`, and `maru trace <task-slug>` for the recorded state.\n"
    )
    summary = artifacts_dir / "human-summary.md"
    summary.write_text("\n".join(sections), encoding="utf-8")
    return summary
