"""Development entrypoint for the MARU relay.

The relay itself lives in :mod:`maru.core.relay` and is driven by ``maru run``. This script
stays as a thin wrapper so existing docs, CI smoke checks and local habits keep working; it
owns no lifecycle of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from maru.core.config import ConfigError
from maru.core.relay import (
    AdapterFactory,
    RelayStopped,
    TestRunner,
    default_adapter_factory,
    git_changed_paths,
    run_relay,
)

__all__ = [
    "AdapterFactory",
    "RelayStopped",
    "TestRunner",
    "default_adapter_factory",
    "git_changed_paths",
    "main",
    "run_relay",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MARU v0.1 proto relay harness.")
    parser.add_argument("slug", help="Task directory name under the configured tasks path")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="MARU project root")
    parser.add_argument(
        "--timeout", type=_positive_float, default=1800, help="Per-agent timeout in seconds"
    )
    parser.add_argument(
        "--test-timeout",
        type=_positive_float,
        default=300,
        help="Per deterministic test command timeout in seconds",
    )
    args = parser.parse_args()
    try:
        summary = run_relay(
            args.root,
            args.slug,
            timeout_s=args.timeout,
            test_timeout_s=args.test_timeout,
        )
    except (RelayStopped, ConfigError) as error:
        print(f"Relay stopped: {error}", file=sys.stderr)
        return 2
    print(summary)
    return 0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
