from __future__ import annotations

import json
import sys
from pathlib import Path

from maru.agents.adapters.claude import ClaudeAdapter
from maru.core.models import AgentRequest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_print_json_success.json"


def _replay_script(tmp_path: Path, stdout_text: str) -> Path:
    """A stand-in CLI that replays recorded stdout, so no live model call is needed."""
    payload = tmp_path / "stdout.txt"
    payload.write_text(stdout_text, encoding="utf-8")
    script = tmp_path / "replay_claude.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.stdin.read()\n"
        f"sys.stdout.write(Path({str(payload)!r}).read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    return script


def test_recorded_claude_envelope_yields_structured_result_session_and_success(tmp_path) -> None:
    """Recorded from a live `claude -p --output-format json --json-schema` run (CLI 2.1.250).

    Only `session_id` and `uuid` were replaced with placeholders; every other field is verbatim.
    """
    script = _replay_script(tmp_path, FIXTURE.read_text(encoding="utf-8"))

    result = ClaudeAdapter(command=[sys.executable, str(script)]).run(
        AgentRequest(role="planner", prompt='Return {"ok": true}'), cwd=tmp_path
    )

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.structured_result == {"ok": True}
    assert result.session_id == "00000000-0000-4000-8000-000000000001"


def test_recorded_envelope_without_structured_output_falls_back_to_the_result_string(
    tmp_path,
) -> None:
    envelope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del envelope["structured_output"]
    envelope["result"] = "```json\n{\"ok\": true}\n```"
    script = _replay_script(tmp_path, json.dumps(envelope))

    result = ClaudeAdapter(command=[sys.executable, str(script)]).run(
        AgentRequest(role="planner", prompt="x"), cwd=tmp_path
    )

    assert result.structured_result == {"ok": True}
    assert result.session_id == envelope["session_id"]
