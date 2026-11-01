from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest

from maru.core.assets import (
    PACKAGED,
    PROJECT_OVERRIDE,
    ROLES,
    SCHEMA_FILES,
    AssetError,
    inventory,
    resolve_prompt,
    resolve_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_default_prompt_and_schema_resolves_from_an_empty_project(tmp_path) -> None:
    """An external repo with no MARU files still gets a complete role set."""
    for role in ROLES:
        prompt = resolve_prompt(tmp_path, role)
        schema = resolve_schema(tmp_path, role)
        assert prompt.source == PACKAGED and prompt.text.strip()
        assert schema.source == PACKAGED
        assert json.loads(schema.text)["type"] == "object"


def test_no_prompts_or_schemas_directory_is_required(tmp_path) -> None:
    resolve_prompt(tmp_path, "planner")
    assert not (tmp_path / "prompts").exists()
    assert not (tmp_path / "schemas").exists()


def test_maru_itself_ships_no_root_prompt_or_schema_copy() -> None:
    """The regression: prompts lived at the repository root and external projects had none."""
    assert not (REPO_ROOT / "prompts").exists()
    assert not (REPO_ROOT / "schemas").exists()


def test_project_override_wins_over_the_packaged_asset(tmp_path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "planner.md").write_text("Project planner.", encoding="utf-8")

    asset = resolve_prompt(tmp_path, "planner")

    assert asset.source == PROJECT_OVERRIDE
    assert asset.text == "Project planner."
    assert resolve_prompt(tmp_path, "worker").source == PACKAGED


def test_schema_override_wins_and_stays_validated(tmp_path) -> None:
    (tmp_path / "schemas").mkdir()
    body = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}
    (tmp_path / "schemas" / SCHEMA_FILES["planner"]).write_text(json.dumps(body), encoding="utf-8")

    assert json.loads(resolve_schema(tmp_path, "planner").text) == body


def test_corrupt_schema_override_fails_clearly_instead_of_falling_back(tmp_path) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / SCHEMA_FILES["planner"]).write_text("{not json", encoding="utf-8")

    with pytest.raises(AssetError, match="Invalid JSON schema"):
        resolve_schema(tmp_path, "planner")


def test_empty_prompt_override_fails_clearly(tmp_path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "worker.md").write_text("   \n", encoding="utf-8")

    with pytest.raises(AssetError, match="Empty project override"):
        resolve_prompt(tmp_path, "worker")


def test_directory_at_the_override_path_fails_clearly(tmp_path) -> None:
    (tmp_path / "prompts" / "reviewer.md").mkdir(parents=True)

    with pytest.raises(AssetError, match="not a file"):
        resolve_prompt(tmp_path, "reviewer")


def test_inventory_names_the_source_of_every_required_asset(tmp_path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "planner.md").write_text("Project planner.", encoding="utf-8")

    rows = dict(inventory(tmp_path))

    assert len(rows) == 2 * len(ROLES)
    assert rows["prompts/planner.md"].startswith(PROJECT_OVERRIDE)
    assert rows["prompts/worker.md"].startswith(PACKAGED)
    assert all("error" not in value for key, value in rows.items() if key != "prompts/planner.md")


def test_inventory_reports_a_broken_override_without_raising(tmp_path) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / SCHEMA_FILES["reviewer"]).write_text("{", encoding="utf-8")

    assert any(value.startswith("error:") for _, value in inventory(tmp_path))


def test_packaged_assets_are_readable_through_the_package_api() -> None:
    """This is exactly how an installed wheel reads them, with no repository checkout."""
    root = files("maru.assets")
    for role in ROLES:
        assert root.joinpath("prompts", f"{role}.md").read_text(encoding="utf-8").strip()
        assert json.loads(root.joinpath("schemas", SCHEMA_FILES[role]).read_text(encoding="utf-8"))


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required to build the wheel")
def test_built_wheel_contains_the_prompt_and_schema_package_data(tmp_path) -> None:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = sorted(tmp_path.glob("*.whl"))
    assert wheels, "uv build produced no wheel"
    names = set(zipfile.ZipFile(wheels[-1]).namelist())

    expected = {f"maru/assets/prompts/{role}.md" for role in ROLES}
    expected |= {f"maru/assets/schemas/{name}" for name in SCHEMA_FILES.values()}
    assert expected <= names
