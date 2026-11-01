from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo.py"


def test_offline_demo_exercises_restart_gate_and_preserved_evidence(tmp_path):
    result = subprocess.run(
        [sys.executable, str(DEMO), "--directory", str(tmp_path / "demo")],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DEMO PASS" in result.stdout
    assert "No model was contacted" in result.stdout
    assert "PAUSED -> replan -> HUMAN_APPROVAL -> MERGED" in result.stdout


def test_demo_refuses_existing_user_data(tmp_path):
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("user data", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(DEMO), "--directory", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "directory must be empty" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "user data"


def test_demo_isolates_inherited_git_repository_and_hooks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    subprocess.run(["git", "init", "-q", str(outside)], check=True)
    before = {
        p.relative_to(outside): p.read_bytes() for p in (outside / ".git").rglob("*") if p.is_file()
    }
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    marker = tmp_path / "hook-ran"
    hook = hooks / "pre-commit"
    hook.write_text(f"#!/bin/sh\necho unexpected > '{marker.as_posix()}'\n", encoding="utf-8")
    hook.chmod(0o755)
    config = tmp_path / "global.gitconfig"
    config.write_text(
        "[core]\n hooksPath = " + json.dumps(hooks.as_posix()) + "\n", encoding="utf-8"
    )
    redirected_index = tmp_path / "outside-index"
    result = subprocess.run(
        [sys.executable, str(DEMO), "--directory", str(tmp_path / "demo")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "GIT_DIR": str(outside / ".git"),
            "GIT_WORK_TREE": str(outside),
            "GIT_INDEX_FILE": str(redirected_index),
            "GIT_CONFIG_GLOBAL": str(config),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after = {
        p.relative_to(outside): p.read_bytes() for p in (outside / ".git").rglob("*") if p.is_file()
    }
    assert before == after
    assert not marker.exists()
    assert not redirected_index.exists()
