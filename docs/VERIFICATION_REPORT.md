# Public release candidate verification

Date: 2026-11-01 (Asia/Seoul). Package: 0.2.0. Decision: **READY_WITH_LIMITATIONS**.
This is a local curated candidate, not a published release. No remote push, public repository
creation or visibility change was performed. A later authorized personal Claude CLI trial is
recorded below; its evidence supersedes the initial readiness-only status.

## Candidate boundary and reused evidence

The original stabilization was locally committed before export. Its 283-pass/1-skip Windows
suite, Ruff/Mypy results, security audit and scanner provenance are prior evidence. They were
read and reused, not rerun in the original repository. The candidate's complete `src/` content
was compared with the stabilized origin and is unchanged. New work comprises the synthetic
demo and three tests, neutral fixture names, public documentation and an explicit file manifest.

The prior private Git directory, execution records and local settings were not copied. This
candidate has independently initialized history and no configured remote. See
[PUBLIC_FILES.txt](../PUBLIC_FILES.txt) for the exact intended release file list and
[release readiness](RELEASE_READINESS.md) for exclusions and rights gates.

## Reused candidate verification before the live trial

Environment: Windows AMD64, CPython 3.12.14, uv 0.12.7, Git 2.55.0.windows.2.
A new `.venv` was created in this checkout; 27 locked packages installed successfully.

| Command / check | Result |
|---|---|
| `uv sync --locked` | PASS; fresh candidate environment |
| `uv run maru --help` | PASS; all CLI commands registered |
| `uv run ruff check .` | PASS |
| `uv run mypy src scripts` | PASS; 26 source files |
| `uv build` | PASS; wheel and source distribution |
| `uv run pytest -q -ra` | **285 passed, 0 failed, 1 skipped**, 108.08 seconds |
| Final demo-only follow-up: `uv run pytest tests/integration/test_demo.py -q` | **3 passed**, 5.30 seconds; after Git-environment isolation fix |
| Runtime source comparison against stabilized origin | No differences |
| Fresh installed-wheel smoke and synthetic demo | PASS; details below |

The full suite was run once. A subsequent independent review found that inherited Git variables
could redirect the demo outside its temporary project. The added regression failed before the
fix. The final demo clears inherited Git target/configuration variables, disables global/system
configuration and uses empty hook/template directories for all its Git operations. The focused
three-test run above checks the final script, including an external sentinel repository and hook.
Ruff on both changed files and Mypy over source/scripts passed again. Runtime package code did
not change; the full suite was not repeated. The full-suite count and focused count overlap and
must not be added together. The skip is
`test_config_rejects_symlink_escape`: Windows denied symlink creation. This case is not a PASS
and needs a host with symlink support. macOS/Linux were not executed locally.

Before integration, two new demo tests failed because the script did not exist. The first
implementation exposed a Windows stdout decoding mismatch; explicit UTF-8 demo output fixed it.
The focused rerun passed both tests, including refusal to overwrite an occupied directory.
An isolated Mypy invocation on only the demo could not resolve the untyped installed package;
the documented `mypy src scripts` command resolves the project source and passed. These interim
failures are not counted as final passes. Existing runtime tests were not rewritten to pass.

## Fresh wheel installation and actual sample execution

A second new environment was created outside the checkout with:

```text
uv venv --python 3.12 <fresh-env>
uv pip install --python <fresh-env-python> <candidate-wheel>
```

Using that environment's installed executable from a separate clean project:

| Operation | Observed result |
|---|---|
| `maru --help` | Exit 0 |
| `maru init` | Exit 0; local state initialized |
| `maru status` | Exit 0; No active arc |
| `maru doctor` | Exit 0; executable/version and packaged-asset diagnostics |
| Malformed TOML then `maru status` | Expected exit 2; no traceback |
| Installed Python runs `scripts/demo.py --directory <new-project>` | Exit 0; DEMO PASS |

The demo exercises CLI request registration, a deliberate Challenger failure, PAUSED state,
resume and replanning, Worker output, a real subprocess check, HUMAN_APPROVAL, blocked rerun,
explicit demo-only approval, MERGED state and retained numbered evidence. It asserts one Arc
and preservation of the first plan. [DEMO.md](DEMO.md) contains a sanitized captured excerpt.
It retains its generated directory rather than deleting evidence.

## Evidence levels: do not combine these claims

| Level | Result |
|---|---|
| Deterministic synthetic demo | PASS; fake role artifacts, real core/CLI/Git/SQLite/test gate |
| Recorded-adapter external-project E2E | PASS in candidate suite |
| Recorded provider-envelope parsing | PASS in candidate suite; historical fixture data |
| Installed local provider CLIs | Live trial: Claude Code 2.1.316; earlier Codex readiness check: 0.160.0 |
| Local authentication-status checks | Both commands exited 0 and reported authenticated; identities/tokens omitted |
| Current model/network connection | **PASS for Claude** in the authorized direct smoke; Codex live remains unverified |
| Real model task completion | **PASS for the bounded Claude calculator task** through HUMAN_APPROVAL; see live evidence below |
| Cross-platform CI | **CI CONFIGURED**, not REMOTE CI VERIFIED |

Read-only readiness checks used `claude --version`, `claude auth status`, `claude --help`,
`codex --version`, `codex login status`, and `codex exec --help`. The installed help lists
Claude's output-format/permission-mode/restricted/json-schema options and Codex's
json/sandbox/output-schema options used by the adapters. Those earlier checks established local command availability only. The later Claude trial below
adds bounded server/task evidence, not a guarantee of quota, model quality or permission isolation.

Defaults route Planner/Worker to Claude and Challenger/Reviewer to Codex. Environment overrides
are executable paths: MARU_CLAUDE_BIN, MARU_CODEX_BIN, MARU_GIT_BIN. MARU does not load `.env`
automatically. Authentication remains external. The default Worker gets workspace-write;
other default roles are read-only. Consult [DEMO.md](DEMO.md) for the executed live trial scope and reproduction recipe.

## README command coverage

Installation/help/static-analysis/build/full-test commands were executed as written in this
checkout. The demo script's new-directory form ran both in its regression and with the installed
wheel; the final default temporary-directory command also passed after Git isolation.
CLI init/run/status/inbox/
resume/approve and expected failure exits ran in the demo. Existing candidate tests exercise
prompt-file input, trace, cost and rejection. The CLI table describes parameterized forms, not
literal commands with placeholder IDs. The live recipe is separately verified below and excluded from offline success claims.
Its authentication and billing scope must be checked again by each user.

## CI and limits

The SHA-pinned workflow configures locked installation, CLI/harness smoke, Ruff, Mypy, build,
and the cost-free unit/integration suite on Ubuntu, macOS and Windows. The action references
were verified during stabilization and did not change here; that evidence is reused. No remote
workflow result is claimed and no success badge was added.

Resume replans rather than continuing an exact instruction. Source changes left by an interrupted
Worker may need manual reconciliation. SQLite and filesystem writes are not one transaction;
latest convenience artifacts remain mutable. Worker guards are not full isolation or rollback.
Use default state paths because some adapters still write under `.maru`. Current adapters do not
populate token counts. No performance, monetary saving or general model-quality benchmark was run.

## Security and release gates

Final candidate-file and new-history scan evidence is recorded in the release-readiness report.
The 89-file export and initial candidate commit `66dc41e` both passed Gitleaks with no findings.
The import's whitespace check reported inherited Markdown hard-break spaces and extra EOF blank
lines; these were retained rather than making unrelated source changes. Ruff and Mypy passed.
Earlier unchanged history/scanner provenance is reused. License selection, ownership confirmation,
public author identity and explicit publication approval remain owner decisions. No LICENSE was
invented, no remote was configured and no private hosted asset was migrated.


## Authorized live Claude trial

Executed 2026-11-01; report updated 2026-11-02 (Asia/Seoul).

This trial used the owner's logged-in personal `claude.ai` subscription through the installed
Claude Code CLI **2.1.316**. No API key, API-token helper, routing environment override or
forced API login was found in the inspected process/user settings. Authentication-status output
was filtered to method/provider/status; account identities and credentials were not saved.
The process ancestry was PowerShell → Codex → desktop application, not a Claude parent.
No nested-session marker was present, no nesting block occurred, and no protection was removed.
`--bare` was not used. Other user sessions were not terminated or modified.

### Direct invocation

```powershell
claude -p "Reply with exactly MARU_LIVE_READY" --output-format json --max-turns 1 --no-session-persistence
```

**PASS**: exit 0, valid JSON, `is_error=false`, subtype `success`, exact result
`MARU_LIVE_READY`, empty stderr, one reported turn, **5.64 seconds**.

### Real MARU coding path

A separate temporary Git repository contained a deliberately incorrect `add(a, b)` returning
`a - b`, an empty `src/__init__.py`, and one pytest test with two addition assertions.
Before execution: **1 failed in 0.19 s**, reporting `add(2, 3) == -1` instead of `5`.
All four roles used the real Claude adapter; fallback, plan revisions and review-fix loops
were disabled. Per-agent timeout was 180 seconds; test-command timeout was 30 seconds.
No adapter factory was replaced and no recorded/synthetic response was injected.

The installed MARU `run` command completed in **51.30 seconds**, exit 0, empty stderr.
The real Worker changed only `src/calculator.py`:

```diff
-    return a - b
+    return a + b
```

The core's configured pytest gate passed. A separate post-run pytest invocation also passed:
**1 passed in 0.03 s**. Git status and diff confirmed no other source/test/config changes.
SQLite held one Arc, four successful AGENT_COMPLETED events and this transition sequence:

```text
PLANNING -> PLAN_REVIEW -> IMPLEMENTING -> TESTING -> CODE_REVIEW -> HUMAN_APPROVAL
```

Raw adapter stdout envelopes, per-stage result files, rendered prompts, numbered artifacts,
test output and SQLite events were retained only in the private temporary workspace. Each
stage had a nonempty provider session identifier and exit 0; identifiers and raw logs are not
published. The inspected model label was `claude-opus-5-5` for all four role envelopes.

| Real CLI stage | Reported turns | Provider-reported duration | Provider-reported USD value |
|---|---:|---:|---:|
| Planner | 3 | 13.823 s | 0.339357 |
| Challenger | 3 | 11.683 s | 0.3309612 |
| Worker | 4 | 6.114 s | 0.1912088 |
| Reviewer | 2 | 4.029 s | 0.317344 |

There were **5 Claude process invocations** total: one direct smoke and four MARU stages.
Envelopes report **13 turns** total; this is not a measured HTTP request count. No retries,
fallback provider or extra model calls were used. The relay's reported USD total was 1.178871;
including smoke (0.150412), it was **1.329283**. These CLI accounting fields are not evidence of
an API invoice or additional subscription charges. Actual billed cost was not verified.

Because every role used Claude, the core correctly recorded **PENDING_INDEPENDENT_AUDIT**,
not VERIFIED. The human gate remains OPEN intentionally. The relay and code-fix E2E passed;
human approval, a Git merge, Codex review and cross-provider independence are not claimed.

### Reliability after live execution

Without another model request, the same live project rejected rerun and resume while its gate
was open, rejected a changed request, and rejected a competing process while its project lock
was held. Each CLI call exited 2. Hash comparison showed all existing task evidence unchanged;
the Arc stayed HUMAN_APPROVAL and the successful stage count stayed four.

Offline failure/safety tests were freshly executed with:

```text
uv run pytest -q tests/unit/test_adapter_process.py tests/unit/test_adapter_parsing.py tests/unit/test_gate_lifecycle.py tests/integration/test_relay_restarts.py tests/integration/test_harness.py::test_relay_turns_adapter_launch_failure_into_human_stop tests/integration/test_harness.py::test_relay_rejects_contradictory_passing_review tests/integration/test_harness.py::test_failed_test_gate_loops_back_through_implementing
```

**21 passed in 19.18 seconds.** This covers timeout, malformed output, adapter launch failure,
failed gates, approval boundaries, repeated evidence and concurrency without provider usage.
No MARU integration defect required a code fix. A one-off inspection helper initially decoded
CLI help as CP949; that was not MARU's UTF-8 adapter path and did not affect live execution.
No new runtime regression test was necessary. The unchanged full suite, Ruff, Mypy and installed
package evidence above are reused; no redundant full-suite run was made for documentation edits.
The seven changed Markdown files passed local-link, private-path/session-ID and Gitleaks checks.
Wheel and sdist were rebuilt successfully after the documentation update. No raw run logs or
credentials entered the public candidate; the file manifest is unchanged.

| Verification target | Final status |
|---|---|
| Unit tests | PASS, prior complete suite reused; relevant failure tests freshly rerun |
| Recorded Adapter E2E | PASS, unchanged candidate evidence reused |
| Claude CLI direct invocation | PASS, live |
| MARU → Claude live integration | PASS, four real subprocess stages |
| Real code modification E2E | PASS through HUMAN_APPROVAL; only authorized source line changed |
| Local package installation | PASS, unchanged runtime evidence reused |
| GitHub remote CI | NOT_VERIFIED |

This is one small Windows task on one installed CLI version. It does not establish general
model reliability, other operating systems or third-party subscription terms. MARU launches a
user's own official CLI; it does not collect, copy or relay subscription credentials. Any hosted
or third-party authentication design requires a separate review of applicable official terms.
