from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from maru.agents.adapters.base import (
    Redactor,
    execute,
    json_object,
    no_redaction,
    prepare_run,
    resolve_command,
)
from maru.core.models import AgentRequest, AgentResult


def cli_schema(path: Path) -> str:
    """Claude CLI 2.1.250 refuses a top-level `$schema` it cannot resolve, so drop just that key.

    Canonical schema files stay untouched on disk; only the argv copy is rewritten.
    """
    schema: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(schema, dict):
        schema.pop("$schema", None)
    return json.dumps(schema)


class ClaudeAdapter:
    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        redactor: Redactor = no_redaction,
    ) -> None:
        self.command = resolve_command(command or (os.environ.get("MARU_CLAUDE_BIN", "claude"),))
        self.redactor = redactor

    def run(
        self,
        request: AgentRequest,
        *,
        cwd: Path,
        timeout_s: float | None = None,
    ) -> AgentResult:
        files = prepare_run(cwd, request)
        permission = "acceptEdits" if request.permission == "workspace-write" else "plan"
        command = [*self.command, "-p", "--output-format", "json", "--permission-mode", permission]
        if request.permission == "workspace-write":
            command.append("--restricted")
        if request.schema_path:
            command += ["--json-schema", cli_schema(request.schema_path)]
        if request.model:
            command += ["--model", request.model]
        output = execute(
            command,
            request,
            cwd=cwd,
            timeout_s=timeout_s,
            files=files,
            redactor=self.redactor,
        )
        envelope = json_object(output.stdout)
        structured = envelope.get("structured_output") if envelope else None
        if structured is None and envelope and isinstance(envelope.get("result"), str):
            structured = json_object(envelope["result"])
        return AgentResult(
            backend="claude",
            role=request.role,
            exit_code=output.exit_code,
            stdout=output.stdout,
            stderr=output.stderr,
            structured_result=structured if isinstance(structured, dict) else None,
            session_id=envelope.get("session_id") if envelope else None,
            started_at=output.started_at,
            finished_at=output.finished_at,
            rendered_prompt_path=files.prompt,
            raw_log_path=files.stdout,
            stderr_path=files.stderr,
        )
