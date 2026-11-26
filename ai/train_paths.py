"""Safety checks shared by the stand-alone, terminal-only checkpoint trainers."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {ROOT / "checkpoints" / "model.npz",
          ROOT / "checkpoints" / "model_torch.pt"}


def candidate_output(parser: argparse.ArgumentParser, path: str, suffix: str) -> str:
    """Don't permit an accidental write to either active model or an ambiguous suffix.

    Resolve symlinks before comparing: otherwise --out ../model.npz (or a
    symlink to it) could bypass the trainer's safety check. The normal path is
    returned so callers can still use a relative path in their output logs.
    """
    target = Path(path).expanduser().resolve()
    if target.suffix != suffix:
        parser.error(f"Candidate output must have a {suffix} suffix")
    if target in ACTIVE:
        parser.error("Active checkpoints are protected; write to checkpoints/candidates/")
    return str(target)
