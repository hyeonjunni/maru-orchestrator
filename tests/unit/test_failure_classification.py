from __future__ import annotations

import pytest

from maru.agents.failures import TIMEOUT_EXIT_CODE, FailureKind, classify


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("You've hit your usage limit.", FailureKind.RESOURCE_EXHAUSTED),
        ("HTTP 429 Too Many Requests", FailureKind.RESOURCE_EXHAUSTED),
        ("error: rate-limit exceeded", FailureKind.RESOURCE_EXHAUSTED),
        ("401 Unauthorized", FailureKind.AUTH),
        ("Please log in with `claude login`", FailureKind.AUTH),
        ("Segmentation fault", FailureKind.PROCESS),
    ],
)
def test_a_failed_stage_gets_a_typed_cause(stderr: str, expected: FailureKind) -> None:
    assert classify(1, "", stderr)[0] is expected


def test_a_timeout_is_classified_from_the_exit_code() -> None:
    assert classify(TIMEOUT_EXIT_CODE, "", "")[0] is FailureKind.TIMEOUT


def test_retry_after_text_is_preserved_when_the_cli_prints_it() -> None:
    kind, retry_after = classify(
        1, "", "You've hit your usage limit. Try again at 2026-08-30T21:00:00Z."
    )

    assert kind is FailureKind.RESOURCE_EXHAUSTED
    assert retry_after == "2026-08-30T21:00:00Z"


def test_a_generic_failure_without_retry_information_reports_none() -> None:
    assert classify(1, "", "boom") == (FailureKind.PROCESS, None)
