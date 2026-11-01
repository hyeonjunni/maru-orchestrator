from __future__ import annotations

import json

import pytest

from maru.core.config import ConfigError, load_config


def test_test_gate_only_config_keeps_default_roles(tmp_path):
    (tmp_path / "maru.toml").write_text(
        '[test_gate]\ncommands = [["python", "-m", "pytest"]]\n', encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert set(config.agents) == {"planner", "challenger", "worker", "reviewer"}
    assert config.agents["worker"].permission == "workspace-write"
    assert config.test_gate.commands == [["python", "-m", "pytest"]]


def test_partial_role_config_preserves_other_roles(tmp_path):
    (tmp_path / "maru.toml").write_text(
        '[agents.worker]\nbackend = "codex"\npermission = "workspace-write"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.agents["worker"].backend == "codex"
    assert config.agents["planner"].backend == "claude"


@pytest.mark.parametrize("field", ["state_dir", "state_db", "tasks"])
@pytest.mark.parametrize("value", ["../outside", ".", ".git/private", "C:/outside"])
def test_config_rejects_unsafe_write_paths(tmp_path, field, value):
    (tmp_path / "maru.toml").write_text(
        f'[agents]\n[paths]\n{field} = {json.dumps(value)}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="paths"):
        load_config(tmp_path)


def test_config_rejects_symlink_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (project / "state").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    (project / "maru.toml").write_text(
        '[agents]\n[paths]\nstate_db = "state/maru.db"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="paths"):
        load_config(project)


def test_invalid_filesystem_path_reports_config_error(tmp_path):
    (tmp_path / "maru.toml").write_text(
        '[paths]\nstate_db = "\\u0000"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="paths.state_db"):
        load_config(tmp_path)
