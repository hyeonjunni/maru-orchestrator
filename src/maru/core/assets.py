from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

ROLES = ("planner", "challenger", "worker", "reviewer")

SCHEMA_FILES = {
    "planner": "plan.schema.json",
    "challenger": "plan_review.schema.json",
    "worker": "implementation.schema.json",
    "reviewer": "review.schema.json",
}

PACKAGED = "packaged"
PROJECT_OVERRIDE = "project override"


class AssetError(RuntimeError):
    """A required prompt or schema could not be resolved."""


@dataclass(frozen=True)
class Asset:
    """One resolved prompt or schema, and where it came from."""

    key: str
    source: str
    origin: str
    text: str


def _packaged_text(kind: str, filename: str) -> str:
    resource = files("maru.assets").joinpath(kind, filename)
    try:
        return resource.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError) as error:
        raise AssetError(
            f"Packaged asset missing: maru/assets/{kind}/{filename} ({error}). "
            "Reinstall MARU; the wheel is incomplete."
        ) from error


def resolve_asset(root: Path, kind: str, filename: str) -> Asset:
    """Project override at ``<root>/<kind>/<filename>`` if present, else the packaged copy.

    An override that exists but cannot be read is an error: MARU never silently falls back
    to the packaged asset, because a half-applied override would run a prompt the project
    did not intend.
    """
    key = f"{kind}/{filename}"
    override = root / kind / filename
    if override.is_file():
        try:
            text = override.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise AssetError(f"Unreadable project override {override}: {error}") from error
        if not text.strip():
            raise AssetError(f"Empty project override: {override}")
        return Asset(key, PROJECT_OVERRIDE, str(override), text)
    if override.exists():
        raise AssetError(f"Project override is not a file: {override}")
    return Asset(key, PACKAGED, f"maru.assets/{key}", _packaged_text(kind, filename))


def resolve_prompt(root: Path, role: str) -> Asset:
    return resolve_asset(root, "prompts", f"{role}.md")


def resolve_schema(root: Path, role: str) -> Asset:
    asset = resolve_asset(root, "schemas", SCHEMA_FILES[role])
    try:
        json.loads(asset.text)
    except json.JSONDecodeError as error:
        raise AssetError(f"Invalid JSON schema at {asset.origin}: {error}") from error
    return asset


def inventory(root: Path) -> list[tuple[str, str]]:
    """``(key, status)`` for every required asset, for ``maru doctor``. Never raises."""
    rows: list[tuple[str, str]] = []
    for role in ROLES:
        for resolve in (resolve_prompt, resolve_schema):
            try:
                asset = resolve(root, role)
            except AssetError as error:
                key = f"prompts/{role}.md" if resolve is resolve_prompt else SCHEMA_FILES[role]
                rows.append((key, f"error: {error}"))
            else:
                rows.append((asset.key, f"{asset.source} ({asset.origin})"))
    return rows
