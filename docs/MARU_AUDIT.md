# MARU architecture and stabilization audit

Review date: 2026-11-01. This public candidate is a curated snapshot of prior private development.
The existing package is version 0.2.0; stabilization preserves its implementation and persisted
contracts while keeping new work within the core CLI/relay scope. No future learning platform,
dashboards or additional agent framework were introduced.

## Architecture

```text
Typer CLI / prototype harness
  -> deterministic relay
       -> configuration + packaged prompts/schemas + input snapshots
       -> Planner -> Challenger -> Worker -> deterministic checks -> Reviewer
       -> human summary + approval gate
       -> SQLite Arc / events / gates
       -> local artifacts, rendered prompts and subprocess logs
  -> Claude / Codex subprocess adapters
```

| Component | Responsibility |
| --- | --- |
| `src/maru/cli/app.py` | Initialization, execution, status, diagnostics, trace, gates and resume |
| `src/maru/core/relay.py` | Ordered stages, validation, bounded retries, execution exclusion and evidence retention |
| `src/maru/core/state_machine.py` | Allowed state transitions, separate from model judgments |
| `src/maru/storage/sqlite.py` | Transactional state/event updates and gate resolution |
| `src/maru/agents/adapters/` | External CLI invocation, structured results, timeout and process cleanup |
| `src/maru/core/inputs.py` | Explicit text snapshots, hashes and provenance |
| `src/maru/core/context.py`, `telemetry.py` | Role-specific context and invocation/byte/duration measurements |
| `src/maru/guard/policy.py` | Protected-path and grading-file policy |

Roles exchange structured artifacts rather than a shared conversation. Model output is
untrusted input to deterministic validation. The executable test gate and human decision are
separate from the model review. A terminal gate state does not perform a Git merge.
Learning/Bridge agents are absent; their isolation remains a design boundary.

## Reproduced problems and focused fixes

| Priority | Failure mechanism | Stabilization change |
| --- | --- | --- |
| P0 | Rerun could restart planning while approval remained unresolved | Reject pending approval on relevant restart paths |
| P0 | Concurrent relays shared the target working tree | Project execution exclusion |
| P1 | Reusing an Arc could overwrite its original request before rejection | Validate request reuse before replacement |
| P1 | Restarted stage counters reused evidence filenames | Preserve numbered prompts, schemas, outputs and logs |
| P1 | Documented partial configuration required an unexpected agents section | Validated default roles |
| P1 | Malformed configuration and tool probes exposed raw failures | Sanitized errors and timeout handling |
| P0 | Configured storage paths could escape the project | Resolved-path containment checks before writes |
| P0 | Previously dirty grading files could obscure additional Worker edits | Cumulative protected-path checks |

These changes use focused regressions and existing fixtures. No dependency or broad refactor
was needed. Prior stabilization test results and fresh public-candidate checks are distinguished
in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md); that report is the authority for executed
commands, counts, skips and environment limitations.

## Feature evidence map

| Feature | Evidence and qualification |
| --- | --- |
| CLI and packaged assets | Prior installed-wheel smoke; CLI/assets tests are included for candidate verification |
| Relay through human approval | Offline external-project integration test exercises real control flow with recorded adapters |
| Test/agent failure handling | Harness, test-gate and typed-blocker regression suites |
| SQLite state and gates | Storage and gate-lifecycle regression suites |
| Recovery | PARTIAL: state restoration and safe restart, not exact checkpoint replay |
| Claude/Codex integration | Adapter contracts and recorded fixtures; current live calls are not verified |
| Context projection | Projection and incremental-review tests; no claimed real-model savings |
| Cross-platform behavior | Windows evidence plus configured Linux/macOS/Windows workflow; remote results unverified |
| Discovery, Bridge, memory, GUI | NOT_IMPLEMENTED and outside this stabilization scope |

The test map identifies reproducible evidence; it does not assert that every test was executed
on every platform. See the verification report before quoting a pass count.

## Reliability and security boundaries

The relay remains a large orchestration function. Splitting it without a concrete need would
add risk to this stabilization. Resume replans using retained state and evidence; it does not
provide exactly-once distributed execution. A crash after source modification may require
manual reconciliation before the dirty-tree guard allows another Worker.

SQLite transactions and filesystem artifacts are not a single atomic transaction. The Worker
runs on the target working tree. Post-execution checks are not an OS sandbox and do not provide
complete rollback. External tools inherit environment variables, and local output is not
redacted by default. Use trusted repositories and inspect logs before sharing them.

Full learning features and general task scheduling remain unimplemented. Context telemetry
is useful for inspection, but no before/after cost, productivity or quality benchmark supports
a performance claim. The existing architecture provides no evidence that a wholesale framework
replacement is necessary.

The strongest demonstrable contribution is inspectable control flow with durable events,
quality gates, targeted failure regressions and reproducible CLI behavior. Publication rights,
license selection and final approval remain separate from technical test results; see
[RELEASE_READINESS.md](RELEASE_READINESS.md).
