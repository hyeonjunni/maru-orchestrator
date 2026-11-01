# Public release candidate verification

## Initial GitHub publication — 2026-11-02

The owner authorized the initial push and necessary CI corrections to
[hyeonjunni/maru-orchestrator](https://github.com/hyeonjunni/maru-orchestrator).
`main` at `80b6256` was pushed after confirming a clean tree, the exact origin, an empty
remote, the curated root `66dc41e`, LICENSE/README inclusion and the existing zero-finding scans.
The repository is publicly readable without login. Description and six implementation-aligned
topics were applied. Korean Markdown, tables, code blocks, MIT identification and the Mermaid
flow were inspected on GitHub. No tag, GitHub Release or visibility change was performed.

[Initial hosted run](https://github.com/hyeonjunni/maru-orchestrator/actions/runs/41323201458):
Ubuntu and macOS each passed all 298 tests, Ruff, Mypy, build and CLI smoke checks.
Windows passed 297 tests but failed the recorded Codex-output replay: its Python helper
encoded Korean fixture text using the host output encoding. Local reproduction with
`PYTHONIOENCODING=cp1252` failed before correction. The helper now writes the fixture bytes
directly; existing assertions remain, with exact stdout and empty stderr checks added.
The focused test then passed under cp1252, and Ruff passed. Production code is unchanged.
[Subsequent commit runs](https://github.com/hyeonjunni/maru-orchestrator/actions/workflows/ci.yml)
are the authoritative hosted result for the correction and these documentation changes.

Prior clean-install, offline demo, package membership, licensing and secret-scan evidence below
is reused; no paid model trial or redundant local whole-suite run was added. The final hosted
matrix validates the complete suite. Historical preparation checkpoints below describe the
state before publication and do not supersede this section.

## Korean README and publication preparation — 2026-11-02

**READY_FOR_PUBLICATION_APPROVAL.** This checkpoint supersedes the prior approval-pending,
license-pending, uncommitted-patch and partially green test statements retained below.
No push, force push, visibility change or GitHub Release publication was performed.

### Editorial result

README.md is now Korean-first, with a short introduction, one Mermaid flow, offline start,
project setup, actual Claude execution example, design decisions and a compact scope section.
`humanizer-ko` was used for a draft/edit/fact-preservation pass. Repeated negative contrasts,
promotional adjectives, redundant headings and excessive emphasis were removed. The terminal
summary is explicitly reconstructed from recorded evidence. Local links and code fences were
checked; no badge claims remote CI success. A second English README was unnecessary, avoiding
an additional document that would need synchronized updates.

### Final fresh checks

| Check | Result |
|---|---|
| First requested full rerun after the prior audit | 293 passed, 0 failed, 1 skipped; 122.80 s |
| Independent patch review | 19 files reviewed; one medium Windows filename-alias issue found |
| Alias regression before/after correction | Four cases failed before the fix; all 28 input tests passed afterward |
| Narrow independent follow-up | Two files reviewed; issue addressed, no further findings |
| Final `uv run pytest -q -ra` after that correction | **297 passed, 0 failed, 1 skipped; 123.68 s** |
| `uv run ruff check .` | PASS |
| `uv run mypy src scripts` | PASS; 26 source files |
| `uv build` | PASS; wheel and sdist |
| Fresh Python 3.12 venv + wheel install | PASS; 14 runtime dependencies plus MARU |
| Installed CLI outside the source import path | `--help`, `init`, `status`, `doctor`: exit 0 |
| Installed synthetic demo | PASS through approval and MERGED; no provider model request |
| Recorded Adapter / external-project E2E | PASS in final full suite |
| Package membership and licensing | Wheel: 36 entries, MIT metadata and license text; sdist: 91 entries, exactly 90 public files plus PKG-INFO |
| Public file Gitleaks scan | 90 files, 651,881 bytes at scan, zero findings; subsequent report-only changes scanned separately |
| Markdown links / fences / whitespace | PASS |

The skip is `test_config_rejects_symlink_escape`: this Windows host cannot create the required
symlink. macOS/Linux and hosted GitHub Actions remain unverified. The second whole-suite run
was necessary because independent review found a new input-boundary defect after the first
whole-suite run had passed. Counts overlap and must not be added.

The Windows alias fix rejects computed snapshot names ending in spaces or dots before any
copy. Cases include `manifest.json `, `manifest.json.`, `spec ` and `spec.` with extensionless
input files. This closes the reviewed A6 edge case without broadening the feature set.

Reused evidence: the authorized Claude direct smoke and four-role calculator run, explicit
human approval to MERGED, 53 preserved files and 19 preserved events; dependency-license
inventory and scanner provenance. These were not rerun as paid model trials. No new external
provider CLI audit or live relay was needed; the independent patch review used a native reviewer.

### License, rights and Git preparation

The owner confirmed publication rights, selected MIT, and explicitly approved
`Copyright (c) 2026 hyeonjunni`. LICENSE and package metadata now reflect that decision.
The dependency licenses listed in RELEASE_READINESS.md remain separate upstream obligations.
The new Git author is the owner-confirmed `hyeonjunni <bobo050716@gmail.com>`.

The supplied remote is [hyeonjunni/maru-orchestrator](https://github.com/hyeonjunni/maru-orchestrator).
GitHub metadata reported an empty public repository with default branch `main`; `git ls-remote`
returned no refs. Only MARU-PUBLIC was connected as `origin`. Its curated root is `66dc41e`;
no private-repository Git history was copied. The prior three preparation commits retain their
original synthetic identity. Local publication branch: `main`.

Runtime/test corrections are committed as `5d31edd` (`fix: harden approval and execution
evidence boundaries`). The following publication-preparation commit contains the Korean README,
MIT license, build exclusion, allowlist and updated reports. Final commit IDs and the all-ref
Gitleaks history scan are reported in the handoff after that commit is created.

Remaining approval: explicit permission to push local `main` to the supplied repository.
The GitHub connector reports read-only permission; Git CLI push authentication has not been
tested. Resolve authentication if required after publication is authorized. Hosted CI results
will be available only after an authorized push. Release tagging/publication remains separate.

The rest of this document is retained historical evidence, not the current release gate.

## Final publication gate — 2026-11-02 (Asia/Seoul)

Decision: **READY_WITH_LIMITATIONS**, not permission to publish. Scope is the public
candidate at base commit `6a1eb4c` plus the current audit patch. Changes are not committed;
that base hash alone does not identify the corrected candidate. The original private
repository was not modified. No GitHub repository creation, push, visibility change, release
publication or project-license selection was performed.

### 1. Independent audit

A separate, explicitly authorized Codex CLI source-bundle review completed. The first
attempt was policy-blocked and did not review source. The successful review was static,
without tools/tests, and found nine issues. The current session reproduced and addressed
them and found an additional crash-window approval issue and a packaging-boundary issue. See [MARU_AUDIT.md](MARU_AUDIT.md)
for severity, source locations, reproductions, impact, resolutions and exact coverage.
The independent review covers the baseline; the resulting patch has local regression
validation, not another independent model review. No claim of an independent live calculator
task review or live MARU-to-Codex adapter E2E is made.

### 2. Defects and corrections

Changes are confined to existing relay/process/input/gate/validation/guard code, the planner
contract, related tests and existing documentation. Checks now fail closed on Git-visible
tree mutation; delegated decisions bind to one gate/outcome; grading edits require explicit
file lists; input evidence is reused without overwriting; input filename collisions and
contradictory review classifications are rejected; local task files are explicitly excluded from sdist; exceptional process exits reap children;
blocked-work reporting reflects retained changes; missing gate records cannot restart an
HUMAN_APPROVAL Arc. Governance approval wording now describes the existing manual-action
boundary. No dependency or unrelated refactor was added.

### 3. Human Approval

Before action, retained before/after pytest logs, actual calculator diff, four provider
envelopes, SQLite transitions, evidence level and OPEN gate were inspected. Only
`src/calculator.py` changed (`a - b` to `a + b`); the old test failed once and the corrected
test passed. Four role envelopes had exit 0, success subtype and nonempty session identifiers.
The original state sequence reached HUMAN_APPROVAL with PENDING_INDEPENDENT_AUDIT.

The owner explicitly approved the exact live gate in this chat. The actual installed CLI
command was `maru approve <live-gate-id>` from the retained trial project. It exited 0:
**gate APPROVED, Arc MERGED, zero open gates**. Hash comparison preserved all 53 retained
evidence/source files. All 19 prior events were identical; exactly two events were appended
(gate decision and state transition). No model call, source modification or Git merge/push
occurred. The original PENDING_INDEPENDENT_AUDIT event was preserved, not rewritten.

The reject path was exercised through the existing synthetic/recorded relay fixture and real
CLI: REJECTED is terminal, open gates disappear and active status becomes empty. Approval
and rejection fixtures are part of `test_a_resolved_gate_moves_the_arc_to_a_terminal_state`
in the full-suite run. This is separate from the owner's real approval.

### 4. Fresh verification and reused evidence

| Executed in this audit | Result |
|---|---|
| Targeted regressions before fixes | Observed failures for live child after interrupt, post-check mutation, overwritten input, manifest collision, unbound delegated approval, prose-derived grading permission, contradictory review class, false no-work evidence and missing-gate restart |
| Final-candidate full `uv run pytest -q -ra` — exactly one full run | **289 passed, 3 failed, 1 skipped**, 112.93 s |
| Follow-up `uv run pytest tests/integration/test_relay_restarts.py tests/integration/test_harness.py::test_changes_diff_shows_tracked_edits_and_new_file_contents tests/unit/test_planning_policy.py -q` | **25 passed**, 12.94 s; fixes all three full-run failures and includes the added missing-gate regression |
| Other changed-scope runs | Process 2 passed; input/check boundary 25 passed; delegated CLI 1 passed; guard/allowed grading integration 11 passed; models 6 passed; blocked-work/check integration 14 passed |
| `uv run ruff check .` | PASS |
| `uv run mypy src scripts` | PASS, 26 source files |
| `uv build` | PASS, wheel and sdist; rebuilt after the final runtime change |
| Clean venv + wheel install, outside source import path | PASS; installed help/init/status and synthetic demo completed |
| Recorded-adapter and external-project E2E | PASS in the full run, apart from the explicitly identified fixture expectations below |
| Actual Live E2E approval | PASS after explicit user decision; evidence preserved |

Do not describe the full run as an all-green run. Two failures needed fixture migration to
the new explicit-path/schema contract; one expected the old later guard error but now stops
earlier when a check mutates files. The follow-up updated those expectations and verified
them, plus the approval crash-window fix. Counts overlap and must not be summed. No second
full suite was run, following minimum-sufficient-verification instructions. There are no
unresolved failures in the executed follow-up scope. The unchanged skipped symlink test
requires Windows symlink privileges or another host; it is not a PASS.

The fresh wheel environment resolved 14 runtime dependencies rather than the locked dev
environment's 26 third-party packages. Newer resolved platformdirs/pydantic/pydantic-core/typer
versions were observed; installed smoke passed. The lockfile and dependency declarations did
not change. README CLI/installation commands were checked against current entry points;
the fresh installed demo exercised the quick-start flow. Earlier exact `uv sync --locked`
and default `uv run python scripts/demo.py` execution evidence is reused. No new paid live
relay was run after the planner-schema changes; provider compatibility of that changed
contract has static/schema/fixture evidence only.

Reused evidence: original 285-pass/1-skip candidate report; authorized Claude direct smoke and
four-role task; pre/post calculator pytest logs; scanner version/provenance and SHA-pinned CI
reference review. These are not represented as newly executed tests or a new model benchmark.

### 5. Secrets and public security

Gitleaks 8.30.1 with default rules and full redaction scanned the 89-file manifest export:
**zero findings** (637,783 bytes at that scan). All three reachable candidate commits through
`6a1eb4c` also produced **zero findings** (615,178 bytes). Final documentation/whitespace changes were
scanned separately. No rule suppression was added. Build inspection found 35 wheel entries
and 90 sdist entries, with no private audit transcripts, environments, runtime logs or Git
directory. Runtime evidence and reviewer transcripts remain ignored local material.
This is pattern detection and a reviewed file boundary, not proof that every possible secret
or business-sensitive fact is absent. No remote is configured.

### 6–9. License, publication blockers, portfolio and approvals

MIT is recommended; Apache-2.0's explicit patent/notice terms are compared in
[RELEASE_READINESS.md](RELEASE_READINESS.md). All installed dependency metadata was inventoried;
no dependency code is vendored. Project ownership and rights to every source/prompt/fixture
cannot be established from this repository. The owner must confirm them and select a license
and copyright holder before a LICENSE can be finalized.

GitHub publication remains blocked on those rights/license decisions and explicit permission
to create/push/publish. Hosted Windows/macOS/Linux CI is unverified; local verification is
Windows-only. Public author identity also remains an owner decision. The live Human Approval
decision is complete and is not among remaining approvals.

Both portfolio summaries now distinguish real process control, role handoffs, deterministic
states, test/Human Approval gates, retained evidence, external-project bug fixing and failure
boundaries. The one task plus direct smoke used five Claude processes, 13 reported turns and
USD 1.329283 in CLI accounting fields. These are not additional charges or a general average.
Small-task orchestration overhead and unmeasured optimization opportunities are disclosed.

The retained historical sections below describe earlier checkpoints. The final section above
supersedes their approval-pending and pre-audit status statements.

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
