"""Codex sends `--output-schema` to OpenAI structured outputs in strict mode.

Strict mode rejects any object whose `required` does not list every key in `properties`,
with a 400 `invalid_json_schema`, at *every* nesting level. An optional field is expressed
by making it required and nullable, never by leaving it out of `required`. A schema that
breaks the rule takes down every Codex-backed role in the relay before the model is even
asked, so the rule is checked here rather than discovered at provider call time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import maru.assets

SCHEMAS = Path(maru.assets.__file__).resolve().parent / "schemas"


def _objects(node: Any, where: str) -> list[tuple[str, dict[str, Any]]]:
    """Every JSON-Schema object node reachable from ``node``, with a readable location."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found.append((where, node))
        for key, value in node.items():
            found += _objects(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _objects(value, f"{where}[{index}]")
    return found


def test_every_object_requires_all_of_its_properties() -> None:
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        for where, node in _objects(schema, path.name):
            missing = sorted(set(node["properties"]) - set(node.get("required", [])))
            assert not missing, f"{where}: not in `required`: {', '.join(missing)}"


def test_every_object_forbids_additional_properties() -> None:
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        for where, node in _objects(schema, path.name):
            assert node.get("additionalProperties") is False, f"{where}: not strict"
