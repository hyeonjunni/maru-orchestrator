# Three-minute offline walkthrough

From the source checkout:

```text
uv sync --locked
uv run python scripts/demo.py
```

This is a **synthetic adapter demonstration**, not a live model run or a replay of recorded
model reasoning. It uses MARU's real CLI, state machine, SQLite store, filesystem evidence and
a Python subprocess test gate. It creates a temporary Git repository, changes only that
repository, and retains its evidence. A provider is never launched. The adapter boundary is
temporarily replaced inside this demonstration process, then restored.
Inherited Git target/configuration variables and MARU_GIT_BIN are isolated for the demo;
system/global Git configuration, templates and hooks cannot redirect its Git operations.
The original process environment is restored afterwards. Installed Git and Python executables
are still trusted local tools.

1. The first synthetic Challenger refuses a plan. With zero allowed plan revisions, MARU
   pauses the Arc before any Worker writes source.
2. `resume` restores state. Repeating the same request replans, with a second numbered plan.
3. The synthetic Worker writes `greeting.py`. A real Python process imports `greet()` and
   asserts that it returns `hello, MARU`.
4. The synthetic Reviewer accepts. The Arc waits for approval; another run is rejected.
5. The demo explicitly approves its synthetic gate and checks the terminal state. This
   automated decision is confined to the demo. Live users must review and decide their gates.

## Actual output excerpt

Captured from a fresh environment using the built wheel. Only a generated gate UUID is
replaced by `<gate-id>` below; surrounding table output and paths are omitted for brevity.

```text
SYNTHETIC OFFLINE DEMO: no provider processes, credentials, network or API charges.
Relay stopped: Plan revision limit exceeded
Arc resumed: greeting
Relay stopped: Arc greeting has an open human gate; approve or reject it first
Demo-only approval of synthetic work (live workflows require your decision).
Gate <gate-id>: APPROVED; Arc greeting: MERGED
No active arc
DEMO PASS: PAUSED -> replan -> HUMAN_APPROVAL -> MERGED
Numbered evidence preserved. No model was contacted; provider labels are simulated.
```

Tables may show `CROSS_PROVIDER_REVIEW` because the synthetic artifacts use configured provider
labels. In this demo that is a state-machine classification, **not proof of independent model
review**. Prompt-byte counters also describe synthetic inputs, not a cost benchmark.

## Inspect the evidence

The final line prints the local demo directory. You can instead choose a new or empty directory:

```text
uv run python scripts/demo.py --directory demo-output
```

An occupied directory is refused without overwriting its files. The demo does not delete
generated evidence. `demo-output/` is ignored in this checkout.

Under that project, inspect:

- `tasks/greeting/artifacts/history/planner/001.json` and `002.json`: original and replanned output.
- `tasks/greeting/logs/tests-1.log`: actual deterministic check output.
- `tasks/greeting/artifacts/human-summary.md`: latest summary, not immutable history.
- `.maru/maru.db`: one Arc, its events and its resolved human gate.

With MARU installed and its CLI on PATH, `maru trace greeting` and `maru cost greeting` from
that directory display the corresponding events and telemetry. `MERGED` is a MARU state;
neither the demo approval nor MARU merges source changes into a Git branch.

## Live Claude calculator trial

Executed on 2026-11-01 (Asia/Seoul), documented on 2026-11-02. This is real model execution,
separate from the synthetic walkthrough above. Claude Code 2.1.316 used an existing personal
`claude.ai` subscription. No credentials were copied or relayed, and no `--bare` or nesting
workaround was used.

A deliberately incorrect calculator started with one failing pytest test. MARU called the
real Claude adapter for all four roles. The Worker changed only `return a - b` to `return a + b`.
The core test gate and a post-run test passed. The relay exited 0 in 51.30 seconds and stopped
at HUMAN_APPROVAL, leaving its gate open. Same-provider evidence is PENDING_INDEPENDENT_AUDIT,
not VERIFIED. Codex live execution and user approval are not claimed.

See [verification](VERIFICATION_REPORT.md#authorized-live-claude-trial) for timings, usage and
evidence checks. Raw sessions and logs remain private.

### Reproduce with approved personal usage

This consumes your account's allowance. Obtain permission for that use and the disposable
target first. Use a normal PowerShell terminal, not a nested Claude session. Check
`claude --version` and `claude auth status` locally; do not share raw account output.
Inspect API-key/auth-token/provider-routing variables and applicable Claude settings. Stop if
they would change the intended login or billing method. Never clear a nesting marker to bypass
the CLI's protection. This recipe is not a credential integration for a hosted product.

From the MARU checkout, using PowerShell 7 (UTF-8 without BOM):

```powershell
uv sync --locked
$Python = (Resolve-Path .venv/Scripts/python.exe).Path
$Maru = (Resolve-Path .venv/Scripts/maru.exe).Path
if (Test-Path Env:CLAUDECODE) { throw "Use an independent normal terminal" }
if (Get-ChildItem Env:GIT_* -ErrorAction SilentlyContinue) { throw "Use a terminal without Git redirection variables" }
$Trial = Join-Path $env:TEMP ("maru-live-e2e-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Trial | Out-Null
Set-Location $Trial
New-Item -ItemType Directory -Path src, tests, empty-hooks | Out-Null
Set-Content src/__init__.py -Value '' -Encoding utf8
@'
def add(a: int, b: int) -> int:
    return a - b
'@ | Set-Content src/calculator.py -Encoding utf8
@'
from src.calculator import add

def test_add():
    assert add(2, 3) == 5
    assert add(-2, 3) == 1
'@ | Set-Content tests/test_calculator.py -Encoding utf8
@'
.maru/
tasks/
__pycache__/
.pytest_cache/
empty-hooks/
'@ | Set-Content .gitignore -Encoding utf8
```

Create a configuration using the prepared environment's Python and zero retry loops:

```powershell
$GatePython = $Python.Replace('\', '/')
@"
[agents.planner]
backend = "claude"
permission = "read-only"
[agents.challenger]
backend = "claude"
permission = "read-only"
[agents.worker]
backend = "claude"
permission = "workspace-write"
[agents.reviewer]
backend = "claude"
permission = "read-only"
[provider_policy]
allow_fallback = false
require_independent_review_for_verified = true
[limits]
plan_revisions = 0
review_fix_loops = 0
[test_gate]
commands = [["$GatePython", "-m", "pytest", "-q"]]
"@ | Set-Content maru.toml -Encoding utf8
$EmptyHooks = (Resolve-Path empty-hooks).Path
git init -q --template=$EmptyHooks
git config --local core.hooksPath "$EmptyHooks"
git add -- .gitignore maru.toml src tests
git -c core.hooksPath="$EmptyHooks" -c user.name="MARU live test" -c user.email="live-test@example.invalid" -c commit.gpgsign=false commit -qm "Failing calculator baseline"
& $Python -m pytest -q
if ($LASTEXITCODE -ne 1) { throw "Expected the deliberately failing baseline" }
& $Maru init
& $Maru run "Fix the add function bug so existing pytest tests pass. Modify only src/calculator.py; no test changes, new dependencies, commit, merge or push. MARU Core runs the tests." --slug calculator-fix --timeout 180 --test-timeout 30
if ($LASTEXITCODE -ne 0) { throw "Relay stopped; inspect evidence before another call" }
& $Python -m pytest -q
git diff -- src/calculator.py
git status --short
& $Maru status
& $Maru inbox
```

This recipe follows the executed fixture and CLI flow; the literal documentation block was
not run as a second paid trial. Only `src/calculator.py` should change. Inspect the summary
and event trace, and leave the gate open until you have reviewed the work. This recipe does
not auto-approve, merge or push. Do not retry failed or timed-out attempts indefinitely.

```text
Before: 1 failed
After: 1 passed
State: HUMAN_APPROVAL
Evidence: PENDING_INDEPENDENT_AUDIT
Changed file: src/calculator.py
```

The trial used five Claude process invocations including the one-turn direct smoke, without
fallback or retry. Reported dollar fields are accounting estimates, not proof of additional
charges. Each user must check their own CLI version, authentication, allowance and applicable
terms; one successful task does not guarantee results in another environment.
