# MARU architecture and stabilization audit

## Independent patch re-review — 2026-11-02

A separate Codex native reviewer inspected the final runtime/test/package diff against
`6a1eb4c`, limited to A1–A11. It reviewed 19 files and found one remaining medium issue in
A6: Windows normalizes trailing spaces/dots, so an extensionless input named
`manifest.json ` could alias the manifest despite the casefold collision check.
Four regression cases failed before the fix. Computed names ending in spaces/dots are now
rejected before any copies; all 28 input tests passed. The reviewer then inspected only the
two changed files and approved that narrow fix with no further findings. This is static
independent review; tests were executed by the maintainer and reported separately.
No additional provider CLI/model trial was used for release preparation.

## Final independent review — 2026-11-02

Baseline: public candidate `6a1eb4c`. A separately invoked Codex CLI 0.160.0
(`gpt-6.1-sol`, ChatGPT login) performed a **static source-bundle review**, after explicit
owner approval. The first invocation could not read any repository file: its read-only
PowerShell commands were rejected by the execution policy. It is an incomplete attempt,
not a clean audit. With separate approval, the second model invocation reviewed numbered
source text without tools. A stalled stdin transport was stopped before a network connection
was observed and replaced with file-backed stdin; no sandbox bypass was used.

The reviewed bundle contained AGENTS, master specification, README, package metadata,
verification report, every tracked runtime source/asset, and selected gate/process/restart
tests. Its SHA256 was `b44091378ad5f2b0d3aa8ee4fe6e543f8e952152d3dd36dc217f9bc06d81db9d`.
The CLI reported 47,960 tokens for the blocked attempt and 91,585 for the completed review;
neither figure establishes additional billing. Raw transcripts remain excluded from publication.

Coverage includes all ten requested areas: FSM, approval bypass, post-approval transitions,
SQLite/concurrency, evidence, worker scope, subprocesses, JSON, failure/retry handling and
public security. The reviewer grouped approval and post-approval together in its coverage
table. It did not execute tests, scan Git history, or verify the Live E2E task. The current
session reproduced the actionable findings and applied the bounded fixes below. These fixes
were locally tested; they have not received a second independent model review.

Locations below refer to the reviewed baseline; reproduction describes isolated fixtures,
never mutation of the retained live task.

| ID / severity | File / baseline line | Reproduction and impact | Resolution |
|---|---|---|---|
| A1 High | `src/maru/core/relay.py:789,820` | A passing check rewrites a source/test file after diff capture. Reviewer sees stale content while the workspace differs. | Compare Git tree identities before/after checks; fail closed before Reviewer on mutations or unavailable identity. A formatter must be run separately and its result re-evaluated. |
| A2 High | `src/maru/cli/app.py:299` | An allowlisted generic decision string resolves an unrelated gate or opposite outcome. | Delegation now requires an explicitly allowlisted exact `<gate-id>:APPROVED` or `<gate-id>:REJECTED` token. Wrong/generic bindings leave the gate OPEN. Local CLI identity remains a trust boundary. |
| A3 Medium | `src/maru/storage/sqlite.py:271`; `src/maru/cli/app.py:324` | Approve a protected-action blocker then rerun: the guard still prohibits it. “Authority granted” implied agent capability that did not exist. | Correct the CLI/README: approval records a decision; the human performs protected actions and clears blockers before resume. No new permission override was added. |
| A4 Medium | `src/maru/core/relay.py:278,318,1293`; `src/maru/cli/app.py:147,285` | Worker/checks leave edits, then relay stops. Summary incorrectly asserts no work. | Inspect Git-visible changes on stop; report BLOCKED_WITH_CHANGES or BLOCKED_WORK_UNKNOWN where applicable, retaining no-work wording only when capture finds no changes. Changes may predate the worker; this is workspace evidence, not authorship proof. |
| A5 Medium | `src/maru/core/inputs.py:149` | Change a required source between retries; the snapshot/manifest was overwritten. Earlier evidence could no longer be reconstructed. | Reuse existing valid manifests and snapshots without writing; changed declarations/source/snapshots require a new task slug. |
| A6 Medium | `src/maru/core/inputs.py:149,166` | Input named `manifest` with JSON suffix replaces its own manifest; case-insensitive target collisions also risk corruption. | Preflight all computed names case-insensitively and reject collisions/reserved manifest name before copying. |
| A7 Medium | `src/maru/guard/policy.py:99` | “Do not modify tests/” authorizes grading-file edits through substring matching. | Only exact entries in structured PlanArtifact.writable_paths grant grading-file scope. Updated planner prompt/schema and fixture; absent list grants none. Protected files remain prohibited. |
| A8 Medium | `src/maru/core/models.py:220`; `src/maru/core/relay.py:906` | OUT_OF_SCOPE/NON_BLOCKING entries in the blocking list consume fix iterations. | Reject the contradictory artifact before routing it to a Worker fix loop. |
| A9 Medium | `src/maru/agents/adapters/base.py:116` | Interrupt controller during communicate; child continues after lock unwinds. | Terminate/reap child on exceptional interruption, then re-raise. Regression observed a live child before the fix and a reaped process afterward. |

Additional current-session finding (not attributed to the independent reviewer): **A10 High**,
`src/maru/core/relay.py:_restore_or_create_arc` (baseline line 1129). Reproduce the crash window
after entering HUMAN_APPROVAL but before gate insertion by creating that state without a gate,
then rerunning. The old path restored planning without any human decision. The regression
observed later preflight failure instead of approval refusal, demonstrating that restoration
had already occurred. The minimal fix refuses restart in HUMAN_APPROVAL even when no open
gate exists and requires approval-record reconciliation. It does not fabricate or approve a
gate, and does not make the separate filesystem/database operations atomic.

Additional packaging finding **A11 Medium** (current-session artifact inspection):
`pyproject.toml` lacked an explicit sdist exclusion for local task data. After the scanner
export created `tasks/final-audit/public-scan/.env.example`, the global `!.env.example`
ignore exception allowed that nested example into the sdist. The wheel was unaffected and
the included file contained no secret, but the sdist exceeded the reviewed allowlist.
Reproduction is building with that local export present and listing the tar members.
The minimal fix explicitly excludes `/tasks/**` from sdist; final artifact inspection
checks exact membership against PUBLIC_FILES.txt plus generated PKG-INFO.

The remaining limits are deliberate and disclosed: same-account callers can issue approval
commands or modify local files/SQLite; append-only triggers are not tamper-proof storage;
Git-visible tree checks do not monitor ignored files or external paths; process-tree cleanup
is not OS isolation; filesystem and SQLite commits are not atomic; resume replans. Approval
does not perform Git merge/push. No claim of complete sandboxing or exact checkpoint recovery
is supported. See the final verification section for executed checks and publication gates.

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
| Claude/Codex integration | Claude direct smoke and bounded coding relay verified live on Windows; Codex live remains unverified. See verification report. |
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
