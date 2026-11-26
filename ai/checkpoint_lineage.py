"""Continue candidate training from the last successfully saved compatible weights.

The pointer is content-bound. A missing or changed last checkpoint is an error,
not permission to silently start training from random/old weights. The last
successful candidate of each model format is remembered independently.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .model import HAS_TORCH, HIDDEN, NumpyPolicyValueNet, TorchPolicyValueWrapper
from .env import ACTION_SIZE, INPUT_DIM


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def validate(path: Path) -> None:
    """Catch incompatible/corrupted weights before they become a new candidate."""
    if path.suffix == ".npz":
        net = NumpyPolicyValueNet.load(str(path))
        expected = {"W1": (INPUT_DIM, HIDDEN), "b1": (HIDDEN,),
                    "Wp": (HIDDEN, ACTION_SIZE), "bp": (ACTION_SIZE,),
                    "Wv": (HIDDEN, 1), "bv": (1,)}
        if any(getattr(net, name).shape != shape for name, shape in expected.items()):
            raise ValueError(f"Incompatible NumPy checkpoint: {path}")
    elif path.suffix == ".pt" and HAS_TORCH:
        TorchPolicyValueWrapper(checkpoint=str(path), device="cpu")
    else:
        raise ValueError(f"Cannot resume checkpoint format {path.suffix!r}: {path}")


def _index(directory: Path) -> dict:
    pointer = directory / "latest.json"
    if not pointer.exists():
        return {}
    try:
        saved = json.loads(pointer.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("not an object")
        return saved
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid checkpoint index {pointer}; select a checkpoint explicitly with --resume") from exc


def latest_checkpoint(directory: Path, suffix: str) -> Path | None:
    """Use the recorded success; migrate older candidate folders by mtime."""
    directory = directory.resolve()
    record = _index(directory).get(suffix)
    if record is not None:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError(f"Invalid {suffix} entry in {directory / 'latest.json'}")
        raw = Path(record["path"])
        path = (raw if raw.is_absolute() else directory / raw).resolve()
        if path.suffix != suffix or not path.is_file() or digest(path) != record.get("sha256"):
            raise ValueError(f"Last {suffix} checkpoint is missing or changed: {path}. "
                             "Restore it or use --resume to choose another checkpoint.")
        validate(path)
        return path
    older = [path for path in directory.glob(f"*{suffix}") if path.is_file()]
    if not older:
        return None
    newest = max(older, key=lambda path: (path.stat().st_mtime_ns, path.name)).resolve()
    validate(newest)
    return newest


def remember_checkpoint(directory: Path, path: Path) -> None:
    """Atomically record a completed trainer's output, never an in-progress file."""
    directory = directory.resolve()
    path = path.resolve()
    if path.suffix not in (".npz", ".pt") or not path.is_file():
        raise ValueError(f"No completed checkpoint to remember: {path}")
    validate(path)
    directory.mkdir(parents=True, exist_ok=True)
    saved = _index(directory)
    try:
        name = str(path.relative_to(directory))
    except ValueError:
        name = str(path)
    saved[path.suffix] = {"path": name, "sha256": digest(path)}
    handle, temp = tempfile.mkstemp(prefix=".latest-", suffix=".json", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(saved, stream, indent=2)
        os.replace(temp, directory / "latest.json")
    finally:
        Path(temp).unlink(missing_ok=True)
