from __future__ import annotations

import re
from enum import StrEnum

TIMEOUT_EXIT_CODE = 124


class FailureKind(StrEnum):
    """Why a stage stopped, so a human sees the real cause instead of `exited with 1`."""

    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    AUTH = "AUTH"
    SCHEMA = "SCHEMA"
    PROCESS = "PROCESS"
    TIMEOUT = "TIMEOUT"


_EXHAUSTED = re.compile(
    r"usage limit|rate.?limit|quota|resource_exhausted|too many requests|\b429\b", re.IGNORECASE
)
_AUTH = re.compile(
    r"unauthorized|forbidden|authentication|not logged in|invalid api key|please log ?in"
    r"|\b401\b|\b403\b",
    re.IGNORECASE,
)
_RETRY_AFTER = re.compile(
    r"(?:try again (?:at|after|in)|retry[- ]after:?)\s*([^\n.;]{1,80})", re.IGNORECASE
)


def classify(exit_code: int, stdout: str, stderr: str) -> tuple[FailureKind, str | None]:
    """Map a failed adapter process to a typed cause and any retry-after text it printed."""
    text = f"{stderr}\n{stdout}"
    if exit_code == TIMEOUT_EXIT_CODE or "timed out" in text.lower():
        return FailureKind.TIMEOUT, None
    if _EXHAUSTED.search(text):
        match = _RETRY_AFTER.search(text)
        return FailureKind.RESOURCE_EXHAUSTED, match.group(1).strip() if match else None
    if _AUTH.search(text):
        return FailureKind.AUTH, None
    return FailureKind.PROCESS, None
