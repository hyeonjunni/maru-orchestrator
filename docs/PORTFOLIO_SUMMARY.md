# MARU engineering portfolio

[한국어](PORTFOLIO_SUMMARY.ko.md)

MARU is a local development CLI that coordinates LLM agents through structured handoffs,
deterministic checks, SQLite state and human approval. It addresses the manual work of moving
requests between a planner, implementer and reviewer while retaining the evidence behind each step.
This is an AI-assisted engineering project; these cases describe repository findings and
reproducible tests, not production incidents or measured business impact.

## Evidence and scope

The stabilization baseline recorded **283 passed, 1 skipped on Windows**. This is historical
evidence, not a new result for the public release candidate. Use
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) for the current candidate's commands, counts,
installation checks and platform gaps. Tests use temporary repositories and recorded or fake
adapters. A subsequent authorized Claude CLI trial fixed a calculator bug through the real relay,
changed pytest from failure to pass, and reached HUMAN_APPROVAL in 51.30 seconds. All four roles
used Claude, so independent review remains pending. No productivity gain or monetary saving is claimed.

The implementation already includes 0.2.0 context and governance features. Stabilization preserves
them while keeping new work within the core CLI/relay scope. Learning agents, a task scheduler,
memory consolidation and dashboards remain outside the implemented product.

## 1. Closing approval bypasses on retry and resume

**Problem.** An Arc waiting for a human decision could re-enter planning through another `run`
or `resume` invocation.

**Root Cause.** Restart code checked terminal states but not open gates. Resume checked only
whether the Arc was paused. Neither condition represented outstanding human authority.

**Technical Decision.** Enforce pending approval at both execution entry points, before agent
calls or state transitions. Keep the approval decision in the durable store.

**Implementation.** `_restore_or_create_arc` in [relay.py](../src/maru/core/relay.py) rejects open
gates. `resume_arc` in [sqlite.py](../src/maru/storage/sqlite.py) checks gates inside the same
`BEGIN IMMEDIATE` transaction as its transition. The CLI reports the refusal.

**Verification Evidence.** [test_relay_restarts.py](../tests/integration/test_relay_restarts.py)
tests PAUSED and HUMAN_APPROVAL reruns, asserts zero adapter calls and unchanged events, and
tests resume refusal. [test_gate_lifecycle.py](../tests/unit/test_gate_lifecycle.py) retains
coverage of resume after approval.

**Trade-offs.** An unresolved gate deliberately stops progress. Approving a governance blocker
grants authority; it does not mark an unwritten implementation complete or merge Git changes.

**Lessons Learned.** Authorization belongs on recovery paths as well as the normal happy path.

## 2. Matching concurrency control to the shared resource

**Problem.** Two relay processes could operate on the same working tree and private diff index.

**Root Cause.** SQLite serialized individual updates, but an agent invocation and its filesystem
effects span many transactions. Database serialization did not serialize project execution.

**Technical Decision.** Allow one relay per configured project state directory using an OS-owned
file lock. Reject contention immediately rather than introduce a queue or a distributed lease.

**Implementation.** `project_lock` in [relay.py](../src/maru/core/relay.py) uses `msvcrt.locking`
on Windows and `fcntl.flock` on POSIX. Public `start_run` and `run_relay` acquire it separately.
Context-manager cleanup releases ownership on exceptions; the lock file's presence is not ownership.

**Verification Evidence.** `test_project_lock_rejects_other_process_and_releases_on_error`
launches a competing Python process, checks refusal before request creation, then confirms
the project can be used after an exception releases the lock.

**Trade-offs.** Independent Arcs in one project also serialize. This is a local-process mechanism;
network filesystem behavior and distributed coordination are not validated. Configuration must
remain stable during execution. Windows test evidence does not establish POSIX execution success.

**Lessons Learned.** Lock scope must cover the working tree, not just the state row being updated.

## 3. Preserving requests and execution evidence across restarts

**Problem.** Reusing a slug could overwrite the request before a terminal-state check. Restarted
stage counters reused filenames described as immutable history.

**Root Cause.** Input persistence preceded lifecycle validation, and artifact numbering lived in
process-local dictionaries initialized on every call.

**Technical Decision.** Permit identical request reuse, require a new slug for a different request,
and continue evidence numbering from existing files.

**Implementation.** `start_run` compares existing request text before writing. The relay discovers
prior rendered-stage and review numbers, then allocates later prompt, schema, history and test-log
paths. `DIFF_CAPTURED` references the numbered `full.diff` instead of the mutable latest diff.

**Verification Evidence.** `test_request_reuse_preserves_original_bytes` compares bytes before and
after conflicting reuse. `test_restart_preserves_numbered_evidence` runs two failing relays and
checks that earlier numbered files retain their bytes and later logs contain the second result.
Both tests are in [test_relay_restarts.py](../tests/integration/test_relay_restarts.py).

**Trade-offs.** History consumes disk. Latest convenience files and human summaries remain mutable.
SQLite and filesystem writes do not form one atomic transaction; manual history deletion and sudden
interruption are not covered by the normal-rerun preservation guarantee.

**Lessons Learned.** Durable state needs durable artifact identity; append-only events alone cannot
preserve evidence if their referenced files are replaced.

## 4. Defining a recovery contract that the implementation can support

**Problem.** A paused workflow needs a recoverable state and an explanation of why it stopped.
The word “resume” can also imply continuation from the exact interrupted agent step.

**Root Cause.** Model sessions are transient. Persistent Arc state, agent execution and source
modifications have different lifetimes and cannot be treated as one recoverable operation.

**Technical Decision.** Persist transitions and gate decisions transactionally, retain evidence,
and document restart behavior explicitly. Keep the clean-tree guard rather than automatically
discarding or adopting source changes after an interruption.

**Implementation.** [sqlite.py](../src/maru/storage/sqlite.py) records state changes with events.
`resume_arc` reads the transition into PAUSED and restores its preceding state. The next relay run
re-enters planning for the same Arc; it does not replay an exact checkpoint.

**Verification Evidence.** [test_core_storage.py](../tests/unit/test_core_storage.py) checks
pre-pause state restoration. `test_a_paused_relay_resumes_and_never_creates_a_second_arc` in
[test_external_project.py](../tests/integration/test_external_project.py) covers a missing-input
stop, repair and restart with one Arc. Other tests preserve genuine user source modifications.

**Trade-offs.** Interruption after Worker edits can require manual source reconciliation. Exactly-once
agent execution and atomic database/filesystem recovery are unfinished.

**Lessons Learned.** Recovery claims must name the recovered unit: state and evidence are supported;
exact execution continuation requires additional design and failure testing.

## 5. Separating deterministic control from LLM judgment

**Problem.** A plausible model answer does not prove a valid transition or a passing implementation.

**Root Cause.** Model output is variable and may be malformed, contradictory or incomplete. Letting
that output directly choose execution privileges would also make failure behavior hard to test.

**Technical Decision.** Keep transition rules, retry limits, tests and approval in Python. Use
validated artifacts to connect Planner, Challenger, Worker and Reviewer.

**Implementation.** [state_machine.py](../src/maru/core/state_machine.py) declares allowed
transitions; [models.py](../src/maru/core/models.py) defines Pydantic contracts. The relay validates
results, classifies blockers and runs configured argv checks through
[testgate.py](../src/maru/core/testgate.py). Role context projection limits shared material without
combining role conversations. A passing review still requires a passing deterministic gate.

**Verification Evidence.** [test_harness.py](../tests/integration/test_harness.py) covers malformed
artifacts, contradictory reviews and revision limits. [test_test_gate.py](../tests/unit/test_test_gate.py)
checks declaration order, failure propagation and refusal when checks are absent.

**Trade-offs.** This validates contracts and configured checks, not the truth of every plan. Worker
guards run after execution and do not provide OS isolation or complete rollback. Current adapters
do not populate token counts, so prompt-byte telemetry is not a monetary cost measurement.

**Lessons Learned.** Model reasoning can remain flexible while execution authority stays explicit.

## 6. Using tests and static analysis to verify different failure classes

**Problem.** The audit found working-looking paths that existing tests did not constrain, including
approval bypass, history replacement and the documented partial configuration.

**Root Cause.** Happy-path success and interface existence did not exercise retry boundaries or
invalid inputs. Types and lint rules cannot prove those runtime properties.

**Technical Decision.** Add regression tests for reproduced defects, run changed-scope checks during
implementation, then run one final suite. Keep real provider calls separate from offline evidence.

**Implementation.** Pytest fixtures create temporary repositories and scripted subprocesses.
Configuration tests exercise unsafe paths and sanitized errors. Ruff and strict Mypy check source
quality and types. The [CI workflow](../.github/workflows/ci.yml) runs installation, CLI smoke,
static checks, build and tests on three OS targets with SHA-pinned actions.

**Verification Evidence.** The stabilization report records six initially failing relay regressions
and 21 initially failing CLI/config regressions. Its Windows baseline finished at 283 passed and
one symlink-privilege skip. Current public-candidate results are maintained only in
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

**Trade-offs.** Fake adapters make control failures reproducible without provider charges, but cannot
establish live authentication or model quality. A configured CI matrix does not prove remote runs passed.

**Lessons Learned.** Each claim needs matching evidence: behavior tests, type analysis, installed
execution and hosted CI answer different questions.

## 7. Treating installation and CLI examples as executable interfaces

**Problem.** A test-gate-only configuration shown in the setup instructions failed because agent
roles were required. Editable-checkout success also left packaged asset availability uncertain.

**Root Cause.** Documentation, configuration defaults and the installed distribution had not been
validated together. Config parsing and tool-version timeout exceptions escaped into the CLI.

**Technical Decision.** Preserve the existing commands and build stack; supply default roles,
return actionable errors, and verify a wheel outside the checkout.

**Implementation.** [config.py](../src/maru/core/config.py) merges missing roles with defaults and
validates contained paths. [app.py](../src/maru/cli/app.py) converts configuration failures to exit
code 2 and handles version-probe timeouts. [pyproject.toml](../pyproject.toml) defines the `maru`
entry point and Hatchling wheel; prompts and schemas live inside the package.

**Verification Evidence.** [test_config.py](../tests/unit/test_config.py) covers partial TOML.
The stabilization report records fresh-wheel installation followed by help, init, status, doctor
and malformed-config checks outside the checkout, plus inspection of four prompts and four schemas.
Current candidate installation evidence belongs in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

**Trade-offs.** Python 3.12+ and external agent CLIs remain prerequisites for live use. Default
`.maru` paths are recommended because some adapter/constitution paths still ignore custom `state_dir`.

**Lessons Learned.** A README command is part of the product contract; test it as an external user.

## Three cases to lead with

1. **Approval bypass:** a concrete authority failure, two recovery entry points and tests proving
   that no agent starts before the required decision.
2. **Concurrent execution:** the distinction between transaction consistency and working-tree
   ownership, implemented with a bounded local lock.
3. **Evidence preservation:** the mismatch between append-only events and overwriteable files,
   resolved with request identity and persistent numbering.

## Five core technologies

| Technology | Engineering responsibility |
|---|---|
| Python 3.12 and standard-library process/locking APIs | Deterministic relay, argv execution, timeouts and local exclusion |
| SQLite | Transactional Arc state, append-only events and human gate lifecycle |
| Pydantic v2 | Configuration and structured agent-result validation |
| Typer and Rich | CLI entry points, readable state and actionable errors |
| uv, Hatchling, Pytest, Ruff, Mypy and GitHub Actions | Reproducible environment, package build and layered validation |

## Application-ready summary

> Built MARU, an AI-assisted local development CLI with structured agent handoffs, a deterministic
> state machine, SQLite history and executable quality gates. Reproduced and corrected approval
> bypasses, concurrent execution risks and restart evidence overwrites. Added focused regression
> coverage and verified installed-package usage. A live four-role Claude relay corrected a
> calculator bug, passed the existing test and reached human approval; independent review and
> exact checkpoint recovery remain explicit limits.

For an interview demonstration, run the offline external-project relay test from the verification
report, then show a pending gate refusal and the retained numbered evidence. No before/after cost,
latency or productivity benchmark has been completed. Future work should prioritize checkpoint
recovery, stronger execution isolation and cross-provider/platform validation over additional agents.
