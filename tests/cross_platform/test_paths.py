from __future__ import annotations

import sqlite3

from typer.testing import CliRunner

from maru.cli.app import app


def test_init_supports_korean_and_space_path(tmp_path, monkeypatch) -> None:
    project = tmp_path / "한글 project"
    project.mkdir()
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["init"])

    database = project / ".maru" / "maru.db"
    assert result.exit_code == 0
    assert database.is_file()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)

