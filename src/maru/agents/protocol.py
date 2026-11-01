from __future__ import annotations

from pathlib import Path
from typing import Protocol

from maru.core.models import AgentRequest, AgentResult


class AgentAdapter(Protocol):
    def run(
        self,
        request: AgentRequest,
        *,
        cwd: Path,
        timeout_s: float | None = None,
    ) -> AgentResult: ...

