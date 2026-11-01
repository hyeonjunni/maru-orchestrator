from __future__ import annotations

import json
from pathlib import Path

import maru.assets
from maru.agents.adapters.claude import cli_schema

SCHEMAS = Path(maru.assets.__file__).resolve().parent / "schemas"


def test_top_level_schema_declaration_is_dropped_but_structure_survives() -> None:
    """Claude CLI 2.1.250 rejects `$schema: .../draft/2020-12/schema` as an unresolvable ref."""
    canonical = SCHEMAS / "plan.schema.json"

    sent = json.loads(cli_schema(canonical))

    canonical_body = json.loads(canonical.read_text("utf-8"))
    assert "$schema" not in sent
    assert sent == {k: v for k, v in canonical_body.items() if k != "$schema"}


def test_every_canonical_schema_keeps_its_validation_keywords() -> None:
    for canonical in sorted(SCHEMAS.glob("*.schema.json")):
        sent = json.loads(cli_schema(canonical))
        assert sent["type"] == "object"
        assert sent["additionalProperties"] is False
        assert sent["required"]
        assert sent["properties"]


def test_canonical_schema_files_are_not_modified_on_disk() -> None:
    before = {p: p.read_bytes() for p in sorted(SCHEMAS.glob("*.schema.json"))}

    for path in before:
        cli_schema(path)

    assert {p: p.read_bytes() for p in before} == before
    assert all(b'"$schema"' in body for body in before.values())
