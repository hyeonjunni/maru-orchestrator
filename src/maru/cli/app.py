from __future__ import annotations

import json
import locale
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from maru.agents.adapters.base import find_executable
from maru.core import telemetry
from maru.core.assets import inventory
from maru.core.config import ConfigError, MaruConfig, load_config
from maru.core.gates import DEFAULT_CONSTITUTION
from maru.core.governance import (
    BlockerClass,
    authorize_delegated,
    delegation_record,
    policy_for,
)
from maru.core.models import ArcState, GateStatus
from maru.core.relay import RelayStopped, run_relay, start_run
from maru.core.testgate import missing_executables
from maru.events.models import MaruEvent
from maru.storage.sqlite import SqliteStore


def configure_output(stream: Any) -> None:
    """Make ``stream`` replace characters it cannot encode instead of raising.

    Agents write UTF-8; a Windows console is frequently cp949 or cp1252. An em dash in a
    Planner's blocker message must never be the reason `maru trace` dies with a
    UnicodeEncodeError, taking the audit trail with it.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace")
    except (OSError, ValueError):  # pragma: no cover - a stream that refuses is still usable
        pass


for _stream in (sys.stdout, sys.stderr):
    configure_output(_stream)

app = typer.Typer(no_args_is_help=True, help="MARU deterministic agent relay.")
console = Console()


def _context() -> tuple[Path, MaruConfig, SqliteStore]:
    root = Path.cwd()
    try:
        config = load_config(root)
    except ConfigError as error:
        raise typer.BadParameter(str(error)) from error
    return root, config, SqliteStore(root / config.paths.state_db)


@app.command()
def init() -> None:
    """Initialize MARU state in the current project."""
    root, _, store = _context()
    maru_dir = root / ".maru"
    maru_dir.mkdir(parents=True, exist_ok=True)
    constitution = maru_dir / "constitution.md"
    if not constitution.exists():
        constitution.write_text(DEFAULT_CONSTITUTION, encoding="utf-8")
    store.initialize()
    console.print(f"Initialized MARU at {maru_dir}")


@app.command("run")
def run_command(
    slug: Annotated[str, typer.Option("--slug", help="Task slug; also the Arc id.")],
    goal: Annotated[str | None, typer.Argument(help="Goal to relay, instead of a file.")] = None,
    prompt_file: Annotated[
        Path | None, typer.Option("--prompt-file", exists=True, dir_okay=False, readable=True)
    ] = None,
    timeout: Annotated[float, typer.Option("--timeout", min=0.001)] = 1800,
    test_timeout: Annotated[float, typer.Option("--test-timeout", min=0.001)] = 300,
) -> None:
    """Run the full relay for one task slug: Planner, Challenger, Worker, checks, Reviewer.

    One request is one Arc. The request is snapshotted into the task directory and the whole
    relay runs against that single Arc, so no orphan Arc is ever created.
    """
    root = Path.cwd()
    task_dir = root
    try:
        task_dir = start_run(root, slug, prompt_file=prompt_file, goal=goal)
        summary = run_relay(root, slug, timeout_s=timeout, test_timeout_s=test_timeout)
    except ConfigError as error:
        raise typer.BadParameter(str(error)) from error
    except RelayStopped as error:
        console.print(f"Relay stopped: {error}")
        stopped = task_dir / "artifacts" / "human-summary.md"
        if stopped.is_file():
            console.print(f"Human summary: {stopped}")
        raise typer.Exit(code=2) from error
    console.print(f"Human summary: {summary}")


@app.command()
def status() -> None:
    """Show the most recently updated active Arc."""
    _, config, store = _context()
    if not store.path.exists():
        console.print("No active arc")
        return
    arcs = store.list_active_arcs()
    if not arcs:
        console.print("No active arc")
        return
    arc = arcs[0]
    table = Table(title="Active Arc", title_justify="left", show_header=False)
    # Fixed label column keeps the Arc ID unwrapped; the value column folds long goals.
    table.add_column("Field", width=13, no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("Arc", arc.id)
    table.add_row("Goal", arc.goal)
    table.add_row("State", arc.state.value)
    table.add_row("Current agent", arc.current_agent or "-")
    table.add_row("Next step", arc.next_step or "-")
    table.add_row("Open gates", str(len(store.list_open_gates(arc.id))))
    events = store.list_events(arc.id)
    evidence = _latest(events, "EVIDENCE_ASSESSED", "evidence_level")
    raised = _latest_payload(events, "BLOCKER_RAISED")
    if evidence:
        table.add_row("Evidence", evidence)
    # A blocker only describes the Arc's *current* standing when the relay actually stopped on
    # it. A plan-quality blocker that was handed back for a revision is history, not status.
    if raised is not None and arc.state is ArcState.PAUSED:
        blocker = BlockerClass(str(raised.get("blocker", BlockerClass.OTHER.value)))
        policy = policy_for(blocker)
        table.add_row(
            "Blocker",
            f"{blocker.value} raised by {raised.get('role', 'core')} (owner {policy.owner}, "
            f"{'consumes' if policy.fixable_by_revision else 'does not consume'} plan revision)",
        )
        table.add_row(
            "Work done",
            "none; no implementation was performed"
            if evidence == "BLOCKED_NO_IMPLEMENTATION"
            else "completion blocked; inspect workspace changes",
        )
        if policy.requires_decision:
            table.add_row(
                "Decision", "Governance escalation: a human must approve or reject this Arc"
            )
    # The label column is 13 wide so the Arc id never wraps: keep these names short.
    table.add_row(
        "Context",
        f"role projection {'on' if config.context.role_projection else 'off'}, "
        f"review diff {config.context.review_mode}, "
        f"max packet {config.context.max_packet_bytes // 1024} KiB",
    )
    cost = telemetry.summarize(events)
    if cost.prompt_bytes:
        table.add_row(
            "Cost",
            ", ".join(
                f"{role} {entry.prompt_bytes / 1024:.0f} KiB" for role, entry in cost.roles.items()
            ),
        )
    console.print(table)


def _latest(events: list[MaruEvent], event_type: str, key: str) -> str | None:
    values = [event.payload.get(key) for event in events if event.type == event_type]
    return str(values[-1]) if values else None


def _latest_payload(events: list[MaruEvent], event_type: str) -> dict[str, Any] | None:
    payloads = [event.payload for event in events if event.type == event_type]
    return payloads[-1] if payloads else None


@app.command()
def cost(arc_id: str) -> None:
    """Report per-role invocation and context cost for one Arc."""
    _, _, store = _context()
    events = store.list_events(arc_id) if store.path.exists() else []
    if not events:
        console.print("No events found")
        return
    console.print(telemetry.render(telemetry.summarize(events)))


@app.command()
def doctor() -> None:
    """Report local runtime and agent CLI availability."""
    root, config, _ = _context()
    fields = {
        "OS": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "Python": platform.python_version(),
        "Git": _tool_version(os.environ.get("MARU_GIT_BIN", "git")),
        "Claude": _tool_version(os.environ.get("MARU_CLAUDE_BIN", "claude")),
        "Codex": _tool_version(os.environ.get("MARU_CODEX_BIN", "codex")),
        "UTF-8": (
            f"filesystem={sys.getfilesystemencoding()}, "
            f"locale={locale.getpreferredencoding(False)}"
        ),
        "Config": str(root / "maru.toml"),
        "Database": str(root / config.paths.state_db),
    }
    fields |= dict(inventory(root))
    fields["Test gate"] = _test_gate_status(config)
    fields["Providers"] = "; ".join(
        f"{role}: {settings.backend}"
        + (
            f" -> fallback {', '.join(settings.fallback)}"
            if settings.fallback and config.provider_policy.allow_fallback
            else ""
        )
        for role, settings in config.agents.items()
    )
    fields["Context policy"] = (
        f"role projection {'enabled' if config.context.role_projection else 'disabled'}; "
        f"review diff mode {config.context.review_mode}; "
        f"max packet {config.context.max_packet_bytes // 1024} KiB; "
        f"max diff {config.context.max_diff_bytes // 1024} KiB"
    )
    fields["Delegation"] = (
        f"{config.delegation.actor} ({len(config.delegation.allowed_decisions)} allowed decisions)"
        if config.delegation.enabled
        else "disabled (human decides every gate)"
    )
    table = Table(show_header=False)
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in fields.items():
        table.add_row(key, value)
    console.print(table)


def _test_gate_status(config: MaruConfig) -> str:
    """Deterministic project checks, in order, with whether each executable resolves."""
    commands = config.test_gate.commands
    if not commands:
        return "not configured (add `[test_gate] commands = [[...]]` to maru.toml)"
    missing = set(missing_executables(commands))
    # Parentheses, not brackets: Rich reads `[ok]` as a style tag and swallows it.
    return "; ".join(
        f"{' '.join(command)} ({'MISSING' if command[0] in missing else 'ok'})"
        for command in commands
    )


@app.command()
def trace(identifier: str) -> None:
    """Show append-only events for an Arc or run ID."""
    _, _, store = _context()
    events = store.list_trace(identifier) if store.path.exists() else []
    if not events:
        console.print("No events found")
        return
    for event in events:
        refs = " ".join(str(ref.path) for ref in event.artifact_refs)
        console.print(
            f"{event.timestamp.isoformat()} {event.source} {event.type} "
            f"{json.dumps(event.payload, ensure_ascii=False)}{' ' + refs if refs else ''}"
        )


@app.command()
def inbox() -> None:
    """List open human gates, saying what kind of decision each one is."""
    _, _, store = _context()
    gates = store.list_open_gates() if store.path.exists() else []
    if not gates:
        console.print("Inbox empty")
        return
    for gate in gates:
        console.print(f"{gate.id} {gate.arc_id} {gate.reason}")
        opened = _gate_opened(store, gate.id, gate.arc_id)
        blocker = opened.get("blocker")
        if blocker:
            # A governance escalation and a completed implementation are both "an open gate",
            # and telling them apart must not require reading the event log by hand.
            policy = policy_for(BlockerClass(str(blocker)))
            console.print(f"  Governance decision required - {blocker}")
            console.print(f"  Raised by: {opened.get('role', 'core')} (owner: {policy.owner})")
            console.print(
                "  No implementation was performed for this Arc."
                if opened.get("evidence_level") == "BLOCKED_NO_IMPLEMENTATION"
                else "  Completion is blocked; inspect workspace changes before resuming."
            )
        else:
            level = opened.get("evidence_level", "unknown")
            console.print(f"  Completion approval - evidence {level}")


def _gate_opened(store: SqliteStore, gate_id: str, arc_id: str) -> dict[str, Any]:
    """The GATE_OPENED payload for one gate, which records why the gate exists."""
    for event in store.list_events(arc_id):
        if event.type == "GATE_OPENED" and event.payload.get("gate_id") == gate_id:
            return event.payload
    return {}


def _resolve_gate(gate_id: str, status: GateStatus, decision: str | None) -> None:
    root, config, store = _context()
    actor = "human"
    if decision is not None:
        problem = authorize_delegated(config.delegation, decision)
        if problem is not None:
            raise typer.BadParameter(problem)
        if decision != f"{gate_id}:{status.value}":
            raise typer.BadParameter(
                "Delegated decision must match the exact <gate-id>:<APPROVED|REJECTED> outcome"
            )
        actor = config.delegation.actor
    try:
        gate, arc = store.resolve_gate(gate_id, status, actor=actor)
    except (KeyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    if decision is not None:
        store.append_event(
            MaruEvent(
                arc_id=gate.arc_id,
                source="core",
                type="DELEGATED_DECISION",
                payload=delegation_record(config.delegation, decision, gate.id, status.value),
            )
        )
    state = arc.state.value if arc is not None else "unknown"
    console.print(f"Gate {gate.id}: {gate.status.value}; Arc {gate.arc_id}: {state}")
    if arc is not None and arc.state is ArcState.PAUSED and status is GateStatus.APPROVED:
        # Approving a blocker grants authority; it does not do the work. Say what is left,
        # so an Arc that is still paused on purpose does not read as a no-op decision.
        console.print(
            "Decision recorded; protected actions must be completed by the human. "
            f"Resume with `maru resume {gate.arc_id}` once the blocker is cleared."
        )


@app.command()
def approve(
    gate_id: str,
    decision: Annotated[
        str | None, typer.Option("--decision", help="Delegated decision id from [delegation].")
    ] = None,
) -> None:
    """Approve an open human gate and close its Arc."""
    _resolve_gate(gate_id, GateStatus.APPROVED, decision)


@app.command()
def reject(
    gate_id: str,
    decision: Annotated[
        str | None, typer.Option("--decision", help="Delegated decision id from [delegation].")
    ] = None,
) -> None:
    """Reject an open human gate and close its Arc."""
    _resolve_gate(gate_id, GateStatus.REJECTED, decision)


@app.command()
def resume(arc_id: str) -> None:
    """Resume a paused Arc at its pre-pause state."""
    _, _, store = _context()
    arc = store.get_arc(arc_id) if store.path.exists() else None
    if arc is None:
        raise typer.BadParameter(f"Arc not found: {arc_id}")
    if arc.state is not ArcState.PAUSED:
        raise typer.BadParameter(f"Arc {arc_id} is not PAUSED")
    try:
        store.resume_arc(arc_id, source="human")
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"Arc resumed: {arc_id}")


def _tool_version(command: str) -> str:
    executable = find_executable(command)
    if executable is None:
        return "not found"
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "unavailable (version check timed out after 5 seconds)"
    except OSError as error:
        return f"unavailable ({error})"
    return (result.stdout or result.stderr).strip() or f"exit {result.returncode}"


if __name__ == "__main__":
    app()
