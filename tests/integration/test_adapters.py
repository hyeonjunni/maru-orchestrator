from __future__ import annotations

import json
import sys
from pathlib import Path

import maru.assets
from maru.agents.adapters.claude import ClaudeAdapter
from maru.agents.adapters.codex import CodexAdapter
from maru.core.models import AgentRequest


def _write_fixture(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_claude_adapter_sends_prompt_on_stdin_and_parses_json(tmp_path) -> None:
    fixture = _write_fixture(
        tmp_path / "fake_claude.py",
        """import json, sys
prompt = sys.stdin.buffer.read().decode("utf-8")
print(json.dumps({
    "session_id": "claude-session",
    "structured_output": {"received_prompt": prompt, "argv": sys.argv[1:]}
}))
print("fixture stderr", file=sys.stderr)
""",
    )
    request = AgentRequest(
        role="worker",
        permission="read-only",
        prompt="한글 prompt with spaces",
        schema_path=Path(maru.assets.__file__).parent / "schemas" / "implementation.schema.json",
    )

    result = ClaudeAdapter(command=[sys.executable, str(fixture)]).run(request, cwd=tmp_path)

    assert result.exit_code == 0
    assert result.session_id == "claude-session"
    assert result.structured_result is not None
    assert result.structured_result["received_prompt"] == request.prompt
    assert result.structured_result["argv"][:4] == [
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
    ]
    assert "plan" in result.structured_result["argv"]
    assert "acceptEdits" not in result.structured_result["argv"]
    argv = result.structured_result["argv"]
    sent_schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert "$schema" not in sent_schema  # Claude CLI 2.1.250 cannot resolve the meta-schema ref
    assert sent_schema["required"] and sent_schema["additionalProperties"] is False
    assert result.rendered_prompt_path.read_text(encoding="utf-8") == request.prompt
    assert result.stderr_path.read_text(encoding="utf-8").strip() == "fixture stderr"


def test_codex_adapter_reads_structured_last_message_and_jsonl_session(tmp_path) -> None:
    fixture = _write_fixture(
        tmp_path / "fake_codex.py",
        """import json, sys
from pathlib import Path
prompt = sys.stdin.read()
args = sys.argv[1:]
output = Path(args[args.index("-o") + 1])
output.write_text(json.dumps({"result": "pass", "prompt": prompt, "argv": args}), encoding="utf-8")
print(json.dumps({"type": "thread.started", "thread_id": "codex-session"}))
print(json.dumps({"type": "turn.completed"}))
""",
    )
    request = AgentRequest(
        role="worker",
        permission="read-only",
        prompt="review this safely",
        schema_path=Path("schemas/review.schema.json").resolve(),
    )

    result = CodexAdapter(command=[sys.executable, str(fixture)]).run(request, cwd=tmp_path)

    assert result.exit_code == 0
    assert result.session_id == "codex-session"
    assert result.structured_result is not None
    assert result.structured_result["result"] == "pass"
    assert result.structured_result["prompt"] == request.prompt
    assert result.structured_result["argv"][:3] == ["exec", "--json", "--sandbox"]
    assert "read-only" in result.structured_result["argv"]
    assert result.raw_log_path.read_text(encoding="utf-8").count("\n") == 2


def test_claude_workspace_writer_uses_restricted_executor(tmp_path) -> None:
    fixture = _write_fixture(
        tmp_path / "fake_claude.py",
        """import json, sys
sys.stdin.read()
print(json.dumps({"structured_output": {"argv": sys.argv[1:]}}))
""",
    )
    result = ClaudeAdapter(command=[sys.executable, str(fixture)]).run(
        AgentRequest(role="worker", permission="workspace-write", prompt="edit safely"),
        cwd=tmp_path,
    )

    assert result.structured_result is not None
    assert "--restricted" in result.structured_result["argv"]


def test_codex_maps_a_workspace_write_role_onto_its_own_sandbox(tmp_path) -> None:
    fixture = _write_fixture(
        tmp_path / "fake_codex.py",
        """import json, sys
from pathlib import Path
sys.stdin.read()
args = sys.argv[1:]
Path(args[args.index("-o") + 1]).write_text(json.dumps({"argv": args}), encoding="utf-8")
""",
    )

    result = CodexAdapter(command=[sys.executable, str(fixture)]).run(
        AgentRequest(role="worker", permission="workspace-write", prompt="edit"),
        cwd=tmp_path,
    )

    assert result.structured_result is not None
    argv = result.structured_result["argv"]
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
