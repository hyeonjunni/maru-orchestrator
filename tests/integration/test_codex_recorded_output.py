from __future__ import annotations

import sys
from pathlib import Path

from maru.agents.adapters.codex import CodexAdapter
from maru.core.models import AgentRequest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "live_codex_smoke.stdout.jsonl"


def test_recorded_codex_envelope_extracts_thread_id_without_a_result(tmp_path) -> None:
    """Replay the observed CLI envelope without requiring live Codex access."""
    stdout = tmp_path / "stdout.jsonl"
    stdout.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    script = tmp_path / "replay_codex.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.stdin.read()\n"
        f"sys.stdout.buffer.write(Path({str(stdout)!r}).read_bytes())\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    result = CodexAdapter(command=[sys.executable, str(script)]).run(
        AgentRequest(role="reviewer", permission="read-only", prompt='Return {"ok": true}'),
        cwd=tmp_path,
    )

    assert result.stdout == FIXTURE.read_text(encoding="utf-8")
    assert result.stderr == ""
    assert result.exit_code == 1
    assert result.session_id == "00000000-0000-4000-8000-000000000001"
    assert result.structured_result is None
