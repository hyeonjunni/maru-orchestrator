from __future__ import annotations

import json

import pytest

from maru.core.inputs import (
    MAX_BYTES,
    InputClosureError,
    declarations,
    inventory_text,
    load_manifest,
    snapshot,
    verify_closure,
)


def _declare(task_dir, body: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "inputs.toml").write_text(body, encoding="utf-8")


def _task(tmp_path):
    root = tmp_path / "project"
    task_dir = root / "tasks" / "slug"
    task_dir.mkdir(parents=True)
    return root, task_dir


def test_no_declaration_file_means_no_required_inputs(tmp_path) -> None:
    root, task_dir = _task(tmp_path)

    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    assert manifest.inputs == []
    assert verify_closure(root, manifest) == []
    assert "No external inputs" in inventory_text(manifest)


def test_a_project_local_file_is_snapshotted_and_verifiable(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "spec"\npath = "docs/spec.md"\n')

    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    record = manifest.inputs[0]
    assert record.snapshot_path == "tasks/slug/inputs/spec.md"
    assert (root / record.snapshot_path).read_text(encoding="utf-8") == "# Spec\n"
    assert record.bytes == (root / "docs" / "spec.md").stat().st_size
    assert len(record.sha256) == 64
    assert verify_closure(root, manifest) == []


def test_a_sibling_checkout_file_becomes_an_in_repository_snapshot(tmp_path) -> None:
    """Input-closure regression: Planner cited a sibling path the Worker could not read."""
    root, task_dir = _task(tmp_path)
    sibling = tmp_path / "sample-project" / "docs"
    sibling.mkdir(parents=True)
    (sibling / "E00.md").write_text("baseline notes", encoding="utf-8")
    _declare(
        task_dir,
        f'[[inputs]]\nname = "e00"\npath = {json.dumps(str(sibling / "E00.md"))}\n',
    )

    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    record = manifest.inputs[0]
    assert record.snapshot_path.startswith("tasks/slug/inputs/")
    assert (root / record.snapshot_path).is_file()
    assert record.source_path.endswith("E00.md")
    assert record.snapshot_path in inventory_text(manifest)
    assert "not readable by the Worker" in inventory_text(manifest)


def test_provenance_fields_are_recorded_when_a_probe_supplies_them(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "note.md").write_text("note", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "note"\npath = "note.md"\n')

    manifest = snapshot(
        task_dir,
        declarations(task_dir),
        root=root,
        git_probe=lambda _: ("/repo", "abc123", True),
    )

    record = manifest.inputs[0]
    assert (record.source_git_root, record.source_git_commit, record.source_tracked) == (
        "/repo",
        "abc123",
        True,
    )
    assert record.captured_at is not None


def test_a_directory_input_is_rejected(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "docs").mkdir()
    _declare(task_dir, '[[inputs]]\nname = "docs"\npath = "docs"\n')

    with pytest.raises(InputClosureError, match="is a directory"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_a_missing_input_is_rejected(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    _declare(task_dir, '[[inputs]]\nname = "gone"\npath = "gone.md"\n')

    with pytest.raises(InputClosureError, match="does not exist"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_a_dataset_suffix_is_rejected_by_default(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "train.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "train"\npath = "train.csv"\n')

    with pytest.raises(InputClosureError, match="data or binary suffix"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_an_explicitly_allowed_text_file_with_a_blocked_suffix_is_accepted(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "schema.tsv").write_text("col\tkind\n", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "schema"\npath = "schema.tsv"\nallow = true\n')

    assert snapshot(task_dir, declarations(task_dir), root=root).inputs[0].name == "schema"


def test_a_binary_file_is_rejected_even_when_allowed(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "weights.txt").write_bytes(b"\x00\x01\x02model")
    _declare(task_dir, '[[inputs]]\nname = "weights"\npath = "weights.txt"\nallow = true\n')

    with pytest.raises(InputClosureError, match="is binary"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_a_secret_looking_file_is_never_snapshotted(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / ".env").write_text("TOKEN=1\n", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "env"\npath = ".env"\nallow = true\n')

    with pytest.raises(InputClosureError, match="looks like a secret"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_an_oversized_file_is_rejected(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "huge.md").write_text("x" * (MAX_BYTES + 1), encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "huge"\npath = "huge.md"\n')

    with pytest.raises(InputClosureError, match="over the"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_a_traversing_input_name_is_rejected(tmp_path) -> None:
    _, task_dir = _task(tmp_path)
    _declare(task_dir, '[[inputs]]\nname = "../escape"\npath = "x.md"\n')

    with pytest.raises(InputClosureError, match="plain file name"):
        declarations(task_dir)


def test_duplicate_input_names_are_rejected(tmp_path) -> None:
    _, task_dir = _task(tmp_path)
    _declare(
        task_dir,
        '[[inputs]]\nname = "a"\npath = "x.md"\n[[inputs]]\nname = "a"\npath = "y.md"\n',
    )

    with pytest.raises(InputClosureError, match="duplicate input names"):
        declarations(task_dir)


def test_a_deleted_snapshot_breaks_the_closure(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "spec.md").write_text("spec", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "spec"\npath = "spec.md"\n')
    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    (root / manifest.inputs[0].snapshot_path).unlink()

    assert verify_closure(root, manifest) == ["spec: snapshot missing at tasks/slug/inputs/spec.md"]


def test_a_modified_snapshot_breaks_the_closure(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "spec.md").write_text("spec", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "spec"\npath = "spec.md"\n')
    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    (root / manifest.inputs[0].snapshot_path).write_text("tampered", encoding="utf-8")

    problems = verify_closure(root, manifest)
    assert len(problems) == 1
    assert "snapshot SHA-256 changed since capture" in problems[0]


def test_a_modified_source_breaks_the_closure(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "spec.md").write_text("spec", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "spec"\npath = "spec.md"\n')
    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    (root / "spec.md").write_text("changed underneath the plan", encoding="utf-8")

    problems = verify_closure(root, manifest)
    assert len(problems) == 1
    assert "changed since capture" in problems[0]


def test_the_manifest_round_trips_from_disk(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "spec.md").write_text("spec", encoding="utf-8")
    _declare(task_dir, '[[inputs]]\nname = "spec"\npath = "spec.md"\n')
    written = snapshot(task_dir, declarations(task_dir), root=root)

    assert load_manifest(task_dir).inputs == written.inputs


def test_a_malformed_declaration_file_fails_clearly(tmp_path) -> None:
    _, task_dir = _task(tmp_path)
    _declare(task_dir, "inputs = 3\n")

    with pytest.raises(InputClosureError, match="array of tables"):
        declarations(task_dir)


def _boundary_bytes(character: str) -> bytes:
    """Text where ``character`` starts at byte 8190 and so crosses the old 8192-byte cut."""
    encoded = character.encode("utf-8")
    body = b"a" * 8190 + encoded + b"tail\n"
    assert len(encoded) > 2 and 8190 + len(encoded) > 8192
    return body


def test_a_three_byte_codepoint_crossing_the_old_prefix_boundary_is_accepted(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "findings.md").write_bytes(_boundary_bytes("한"))
    _declare(task_dir, '[[inputs]]\nname = "findings"\npath = "findings.md"\n')

    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    text = (root / manifest.inputs[0].snapshot_path).read_text(encoding="utf-8")
    assert text.endswith("한tail\n")


def test_a_four_byte_codepoint_crossing_the_old_prefix_boundary_is_accepted(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "notes.md").write_bytes(_boundary_bytes("𝄞"))
    _declare(task_dir, '[[inputs]]\nname = "notes"\npath = "notes.md"\n')

    manifest = snapshot(task_dir, declarations(task_dir), root=root)

    text = (root / manifest.inputs[0].snapshot_path).read_text(encoding="utf-8")
    assert text.endswith("𝄞tail\n")


def test_invalid_utf8_beyond_the_old_prefix_boundary_is_still_rejected(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    # A truncated three-byte sequence, past byte 8192 so only a whole-file decode sees it.
    (root / "broken.md").write_bytes(b"a" * 9000 + b"\xed\x95" + b"tail\n")
    _declare(task_dir, '[[inputs]]\nname = "broken"\npath = "broken.md"\n')

    with pytest.raises(InputClosureError, match="is not UTF-8 text"):
        snapshot(task_dir, declarations(task_dir), root=root)


def test_a_null_byte_beyond_the_old_prefix_boundary_is_still_binary(tmp_path) -> None:
    root, task_dir = _task(tmp_path)
    (root / "blob.md").write_bytes(b"a" * 9000 + b"\x00tail\n")
    _declare(task_dir, '[[inputs]]\nname = "blob"\npath = "blob.md"\n')

    with pytest.raises(InputClosureError, match="is binary"):
        snapshot(task_dir, declarations(task_dir), root=root)
