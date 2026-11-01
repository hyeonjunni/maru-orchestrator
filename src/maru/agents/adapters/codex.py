from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from maru.agents.adapters.base import (
    Redactor,
    execute,
    json_object,
    no_redaction,
    prepare_run,
    resolve_command,
)
from maru.core.models import AgentRequest, AgentResult


class CodexAdapter:
    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        redactor: Redactor = no_redaction,
    ) -> None:
        self.command = resolve_command(command or (os.environ.get("MARU_CODEX_BIN", "codex"),))
        self.redactor = redactor

    def run(
        self,
        request: AgentRequest,
        *,
        cwd: Path,
        timeout_s: float | None = None,
    ) -> AgentResult:
        files = prepare_run(cwd, request)
        command = [
            *self.command,
            "exec",
            "--json",
            "--sandbox",
            request.permission,
            "-o",
            str(files.last_message),
        ]
        if request.schema_path:
            command += ["--output-schema", str(request.schema_path)]
        if request.model:
            command += ["--model", request.model]
        command.append("-")
        output = execute(
            command,
            request,
            cwd=cwd,
            timeout_s=timeout_s,
            files=files,
            redactor=self.redactor,
        )
        structured = (
            json_object(files.last_message.read_text(encoding="utf-8"))
            if files.last_message.exists()
            else None
        )
        return AgentResult(
            backend="codex",
            role=request.role,
            exit_code=output.exit_code,
            stdout=output.stdout,
            stderr=output.stderr,
            structured_result=structured,
            session_id=_session_id(output.stdout),
            started_at=output.started_at,
            finished_at=output.finished_at,
            rendered_prompt_path=files.prompt,
            raw_log_path=files.stdout,
            stderr_path=files.stderr,
        )


def _session_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        event = json_object(line)
        if event and event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            return thread_id if isinstance(thread_id, str) else None
    return None
