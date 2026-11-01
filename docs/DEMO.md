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

## Live trial plan — not executed

The smallest useful trial is the same greeting helper in a fresh disposable repository with
`check.py` asserting its return value. Initialize MARU, configure the real check, commit the
baseline and submit the goal through `maru run`. Do not inject `SyntheticAdapter` for this trial.

Before running it, obtain permission for provider charges and the exact disposable target.
Use a bounded plan/review loop, disable provider fallback if spending must remain with one
account, and review the provider's CLI permissions. Defaults use Claude Planner/Worker and
Codex Challenger/Reviewer. Authentication belongs to those CLIs, not to MARU.

Local version/help and authentication-status commands were checked without a model request;
see [verification](VERIFICATION_REPORT.md). Network/model connectivity and live task success
remain unverified. A local logged-in status does not prove quota, billing scope or server access.
