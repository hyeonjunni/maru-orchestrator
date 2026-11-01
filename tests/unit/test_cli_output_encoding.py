"""A console that cannot encode an agent's character must degrade, never crash.

Found by dogfooding: a Planner wrote an em dash into its blocker `details`, and `maru trace`
died with UnicodeEncodeError on a cp949 Windows console - losing the audit trail at exactly
the moment a human was trying to read why the Arc stopped.
"""

from __future__ import annotations

import io

from maru.cli.app import configure_output


def _cp949_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp949", newline="")


def test_an_unencodable_character_raises_before_the_stream_is_configured() -> None:
    stream = _cp949_stream()
    try:
        stream.write("blocker — details")
        stream.flush()
    except UnicodeEncodeError:
        return
    raise AssertionError("expected cp949 to reject the em dash; the fixture no longer reproduces")


def test_configure_output_replaces_what_it_cannot_encode() -> None:
    stream = _cp949_stream()

    configure_output(stream)

    stream.write("blocker — details")
    stream.flush()
    assert stream.buffer.getvalue() == b"blocker ? details"  # type: ignore[attr-defined]


def test_configure_output_ignores_a_stream_that_cannot_be_reconfigured() -> None:
    configure_output(io.BytesIO())
