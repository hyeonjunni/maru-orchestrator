from __future__ import annotations

from maru.agents.adapters.base import json_object

PAYLOAD = {"result": "pass", "findings": []}


def test_plain_object_and_surrounding_whitespace() -> None:
    assert json_object('{"result": "pass", "findings": []}') == PAYLOAD
    assert json_object('\n\t  {"result": "pass", "findings": []}  \n') == PAYLOAD


def test_markdown_fenced_json() -> None:
    assert json_object('```json\n{"result": "pass", "findings": []}\n```') == PAYLOAD
    assert json_object('  ```\n{"result": "pass", "findings": []}```  ') == PAYLOAD


def test_non_objects_and_prose_are_rejected() -> None:
    assert json_object("") is None
    assert json_object("not json") is None
    assert json_object("[1, 2]") is None
    assert json_object('"a string"') is None
    # Deliberately not permissive: no brace-scraping out of surrounding prose.
    assert json_object('Here you go: {"result": "pass"} hope that helps') is None
