from __future__ import annotations

import hashlib
import shutil
import tomllib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from maru.core.models import utc_now

DECLARATION_FILE = "inputs.toml"
MANIFEST_FILE = "manifest.json"
SNAPSHOT_DIR = "inputs"

# A required input is documentation, configuration or source text a role must read.
# Datasets, model weights and secrets are never snapshotted into the repository.
MAX_BYTES = 1_048_576
_BLOCKED_SUFFIXES = frozenset(
    {
        ".7z", ".bin", ".ckpt", ".csv", ".db", ".dll", ".dylib", ".exe", ".feather",
        ".gz", ".h5", ".jpeg", ".jpg", ".joblib", ".key", ".model", ".npy", ".npz",
        ".onnx", ".parquet", ".pb", ".pem", ".pkl", ".png", ".pt", ".pth", ".pyc",
        ".safetensors", ".so", ".tar", ".tsv", ".whl", ".xlsx", ".zip",
    }
)
_BLOCKED_STEMS = frozenset({".env", "credentials", "id_rsa", "id_ed25519", "secrets"})

# Repository root, commit, and whether the source file is tracked there.
GitProbe = Callable[[Path], tuple[str | None, str | None, bool | None]]


class InputClosureError(RuntimeError):
    """A declared required input cannot be made available to every role."""


class InputDeclaration(BaseModel):
    """One explicitly declared file. Directories and globs are never accepted."""

    name: str
    path: Path
    allow: bool = False

    @field_validator("name")
    @classmethod
    def name_is_a_plain_identifier(cls, value: str) -> str:
        if not value.strip() or Path(value).name != value or value in (".", ".."):
            raise ValueError(f"input name must be a plain file name: {value!r}")
        return value


class InputRecord(BaseModel):
    name: str
    source_path: str
    snapshot_path: str
    sha256: str
    bytes: int
    source_git_root: str | None = None
    source_git_commit: str | None = None
    source_tracked: bool | None = None
    captured_at: datetime = Field(default_factory=utc_now)


class InputManifest(BaseModel):
    inputs: list[InputRecord] = Field(default_factory=list)


def declarations(task_dir: Path) -> list[InputDeclaration]:
    """Parse ``inputs.toml``. An absent file means the task declares no external inputs."""
    path = task_dir / DECLARATION_FILE
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as error:
        raise InputClosureError(f"Cannot read {path}: {error}") from error
    raw = data.get("inputs", [])
    if not isinstance(raw, list):
        raise InputClosureError(f"{path}: `inputs` must be an array of tables")
    try:
        declared = [InputDeclaration.model_validate(item) for item in raw]
    except ValueError as error:
        raise InputClosureError(f"{path}: {error}") from error
    names = [item.name for item in declared]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise InputClosureError(f"{path}: duplicate input names: {', '.join(duplicates)}")
    return declared


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _reject_reason(source: Path, declaration: InputDeclaration) -> str | None:
    """Documented admission rule, applied before anything is copied."""
    if source.is_dir():
        return "is a directory; declare individual files"
    if not source.is_file():
        return "does not exist"
    lowered = source.name.lower()
    if lowered in _BLOCKED_STEMS or Path(lowered).stem in _BLOCKED_STEMS:
        return "looks like a secret and is never snapshotted"
    if not declaration.allow and source.suffix.lower() in _BLOCKED_SUFFIXES:
        return (
            f"has a data or binary suffix ({source.suffix}); set allow = true only for a text "
            "file MARU must copy anyway"
        )
    size = source.stat().st_size
    if size > MAX_BYTES:
        return f"is {size} bytes, over the {MAX_BYTES} byte required-input limit"
    # The whole file, never a fixed-size prefix: an arbitrary byte cut lands mid-codepoint
    # and rejects valid UTF-8. Reading it all is affordable because MAX_BYTES caps it at 1 MiB.
    data = source.read_bytes()
    if b"\0" in data:
        return "is binary; required inputs must be text"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "is not UTF-8 text"
    return None


def snapshot(
    task_dir: Path,
    declared: list[InputDeclaration],
    *,
    root: Path,
    git_probe: GitProbe | None = None,
) -> InputManifest:
    """Copy every declared input into the task's input area and record its identity."""
    snapshot_dir = task_dir / SNAPSHOT_DIR
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest = InputManifest()
    for declaration in declared:
        source = declaration.path.expanduser()
        source = source if source.is_absolute() else (root / source)
        reason = _reject_reason(source, declaration)
        if reason is not None:
            raise InputClosureError(f"Required input {declaration.name!r} ({source}) {reason}")
        target = snapshot_dir / f"{declaration.name}{source.suffix}"
        shutil.copyfile(source, target)
        digest, size = _sha256(target)
        git_root, commit, tracked = git_probe(source) if git_probe else (None, None, None)
        manifest.inputs.append(
            InputRecord(
                name=declaration.name,
                source_path=str(source.resolve()),
                snapshot_path=target.resolve().relative_to(root).as_posix(),
                sha256=digest,
                bytes=size,
                source_git_root=git_root,
                source_git_commit=commit,
                source_tracked=tracked,
            )
        )
    (snapshot_dir / MANIFEST_FILE).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest


def load_manifest(task_dir: Path) -> InputManifest:
    path = task_dir / SNAPSHOT_DIR / MANIFEST_FILE
    if not path.is_file():
        raise InputClosureError(f"Input manifest missing: {path}")
    try:
        return InputManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputClosureError(f"Unreadable input manifest {path}: {error}") from error


def verify_closure(root: Path, manifest: InputManifest) -> list[str]:
    """Problems that make the plan impossible for the Worker; empty means the closure holds.

    Every snapshot must still exist, still hash to the recorded digest, and still be readable
    from inside the workspace. When the original source is still reachable it must hash the
    same too, so a plan is never executed against content that changed underneath it.
    """
    problems: list[str] = []
    for record in manifest.inputs:
        snapshot_path = root / record.snapshot_path
        if not snapshot_path.is_file():
            problems.append(f"{record.name}: snapshot missing at {record.snapshot_path}")
            continue
        try:
            digest, _ = _sha256(snapshot_path)
            snapshot_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"{record.name}: snapshot unreadable by the Worker: {error}")
            continue
        if digest != record.sha256:
            problems.append(
                f"{record.name}: snapshot SHA-256 changed since capture "
                f"({digest[:12]} != {record.sha256[:12]})"
            )
            continue
        source = Path(record.source_path)
        if not source.is_file():
            continue
        try:
            source_digest, _ = _sha256(source)
        except OSError:
            continue
        if source_digest != record.sha256:
            problems.append(
                f"{record.name}: source {record.source_path} changed since capture "
                f"({source_digest[:12]} != {record.sha256[:12]})"
            )
    return problems


def inventory_text(manifest: InputManifest) -> str:
    """The block every role sees, so a plan cites the snapshot, not a sibling checkout."""
    if not manifest.inputs:
        return "No external inputs were declared for this task."
    lines = [
        "These files were snapshotted into the repository before planning. Refer to the",
        "snapshot path only; the original location is not readable by the Worker.",
        "",
    ]
    lines += [
        f"- {record.name}: {record.snapshot_path} "
        f"(sha256 {record.sha256[:12]}, {record.bytes} bytes, captured from {record.source_path})"
        for record in manifest.inputs
    ]
    return "\n".join(lines)
