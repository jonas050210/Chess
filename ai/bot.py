"""Playing bot: reliable search by default; gated models are opt-in automatically.

An existing .npz is not evidence of playing strength. Only a checkpoint whose
SHA-256 matches a successful training-gate receipt is used in live games.
CHESS_ENGINE=baseline forces the handcrafted engine for comparisons.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import chess
import numpy as np

from .baseline import BaselineBot
from .mcts import best_move, mcts_search, position_key
from .model import HAS_TORCH, load_net

SIMS = {1: 8, 2: 20, 3: 40, 4: 80, 5: 150}
CACHE_LIMIT = 30000
logger = logging.getLogger(__name__)


def approved_checkpoint(path: str | None) -> bool:
    """An approval must match the *contents*, not just the checkpoint name."""
    if not path or not os.path.isfile(path):
        return False
    receipt = Path(path).with_suffix(".approved.json")
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        report = json.loads(receipt.read_text(encoding="utf-8"))
        gate = report["gate"]
        # An older approval against a weaker level-2 opponent cannot replace
        # today's strongest built-in level-5 search in live games.
        return (report["sha256"] == digest.hexdigest() and
                gate.get("passed") is True and gate.get("baseline_level") == 5)
    except (OSError, ValueError, KeyError, TypeError):
        return False


class AIBot:
    def __init__(self, checkpoint: str | None = None,
                 torch_checkpoint: str | None = None):
        self.engine = "baseline-search"
        self.device = "CPU"
        self.has_checkpoint = False
        self.net = None
        self.baseline = BaselineBot()
        self._root = None
        self._cache: dict = {}
        self.last_error = None

        choice = os.environ.get("CHESS_ENGINE", "auto").lower()
        if choice == "baseline":
            return
        paths = [(torch_checkpoint, "torch-mcts"), (checkpoint, "numpy-mcts")]
        for path, name in paths:
            if path and os.path.isfile(path) and (name != "torch-mcts" or HAS_TORCH):
                if choice != "model" and not approved_checkpoint(path):
                    continue
                try:
                    self.net = load_net(path)
                except (OSError, ValueError, KeyError, RuntimeError):
                    logger.exception("Could not load gated checkpoint %s; using baseline", path)
                    continue
                self.has_checkpoint = True
                self.engine = name
                self.device = getattr(self.net, "device", "CPU")
                break

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def reset(self):
        self._root = None
        self._cache.clear()
        self.baseline.clear()

    def _reusable_root(self, board: chess.Board):
        if self._root is None or not self._root.children:
            return None
        key = position_key(board)
        for child in self._root.children:
            if position_key(child.board) == key:
                child.parent = None
                return child
        return None

    def _search(self, board: chess.Board, level: int, remember: bool, cancel=None):
        level = max(1, min(5, int(level)))
        if not self.has_checkpoint:
            return self.baseline.choose_move(board, level, cancel=cancel)
        cache = self._cache if remember else {}
        root_hint = self._reusable_root(board) if remember else None
        try:
            root, _, _ = mcts_search(
                board, self.net, simulations=SIMS[level], temperature=0.0,
                rng=np.random.default_rng(), noise_eps=0.0,
                cache=cache, root=root_hint, should_stop=cancel,
            )
            move = best_move(root)
            if move is None or not board.is_legal(move):
                raise ValueError("MCTS produced no legal move")
            if remember:
                self._root = next((c for c in root.children if c.move == move), None)
                if len(self._cache) > CACHE_LIMIT:
                    self._cache.clear()
            return move
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("MCTS failed; falling back to search")
            return self.baseline.choose_move(board, level, cancel=cancel)

    def choose_move(self, board: chess.Board, level: int = 3, cancel=None):
        return self._search(board, level, remember=True, cancel=cancel)

    def hint(self, board: chess.Board, level: int = 3, cancel=None):
        return self._search(board, level, remember=False, cancel=cancel)
