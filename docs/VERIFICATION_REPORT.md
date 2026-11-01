# Public release candidate verification

Date: 2026-11-01 (Asia/Seoul). Package: 0.2.0. Decision: **READY_WITH_LIMITATIONS**.
This is a local curated candidate, not a published release. No remote push, public repository
creation, visibility change or model request was performed.

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

## Fresh execution on this candidate

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
| Installed local provider CLIs | Claude Code 2.1.263; Codex CLI 0.160.0 detected |
| Local authentication-status checks | Both commands exited 0 and reported authenticated; identities/tokens omitted |
| Current model/network connection | **NOT VERIFIED**; no inference request sent |
| Real model task completion | **NOT VERIFIED**; requires spending and target approval |
| Cross-platform CI | **CI CONFIGURED**, not REMOTE CI VERIFIED |

Read-only readiness checks used `claude --version`, `claude auth status`, `claude --help`,
`codex --version`, `codex login status`, and `codex exec --help`. The installed help lists
Claude's output-format/permission-mode/restricted/json-schema options and Codex's
json/sandbox/output-schema options used by the adapters. This establishes local command
availability, not current quota, server reachability, model quality or effective permission isolation.

Defaults route Planner/Worker to Claude and Challenger/Reviewer to Codex. Environment overrides
are executable paths: MARU_CLAUDE_BIN, MARU_CODEX_BIN, MARU_GIT_BIN. MARU does not load `.env`
automatically. Authentication remains external. The default Worker gets workspace-write;
other default roles are read-only. Consult [DEMO.md](DEMO.md) for the unexecuted live trial plan.

## README command coverage

Installation/help/static-analysis/build/full-test commands were executed as written in this
checkout. The demo script's new-directory form ran both in its regression and with the installed
wheel; the final default temporary-directory command also passed after Git isolation.
CLI init/run/status/inbox/
resume/approve and expected failure exits ran in the demo. Existing candidate tests exercise
prompt-file input, trace, cost and rejection. The CLI table describes parameterized forms, not
literal commands with placeholder IDs. The live recipe is explicitly NOT EXECUTED and excluded
from offline success claims. Its cost/authentication prerequisite cannot be proved by fake adapters.

## CI and limits

The SHA-pinned workflow configures locked installation, CLI/harness smoke, Ruff, Mypy, build,
and the cost-free unit/integration suite on Ubuntu, macOS and Windows. The action references
were verified during stabilization and did not change here; that evidence is reused. No remote
workflow result is claimed and no success badge was added.

Resume replans rather than continuing an exact instruction. Source changes left by an interrupted
Worker may need manual reconciliation. SQLite and filesystem writes are not one transaction;
latest convenience artifacts remain mutable. Worker guards are not full isolation or rollback.
Use default state paths because some adapters still write under `.maru`. Current adapters do not
populate token counts. No performance, monetary saving or live-model quality benchmark was run.

## Security and release gates

Final candidate-file and new-history scan evidence is recorded in the release-readiness report.
The 89-file export and initial candidate commit `66dc41e` both passed Gitleaks with no findings.
The import's whitespace check reported inherited Markdown hard-break spaces and extra EOF blank
lines; these were retained rather than making unrelated source changes. Ruff and Mypy passed.
Earlier unchanged history/scanner provenance is reused. License selection, ownership confirmation,
public author identity and explicit publication approval remain owner decisions. No LICENSE was
invented, no remote was configured and no private hosted asset was migrated.
