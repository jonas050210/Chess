"""Einheitlicher Bot: Torch/CUDA > NumPy > Negamax. Mit Root-Reuse + Cache."""
from __future__ import annotations

import os
import numpy as np
import chess
from .model import HAS_TORCH, load_net
from .mcts import mcts_search, best_move, position_key
from .baseline import BaselineBot

SIMS = {1: 8, 2: 20, 3: 40, 4: 80, 5: 150}
CACHE_LIMIT = 30000


class AIBot:
    def __init__(self, checkpoint: str | None = None,
                 torch_checkpoint: str | None = None):
        self.engine = "baseline-negamax"
        self.device = "CPU"
        self.has_checkpoint = False
        self.net = load_net(None)
        self.baseline = BaselineBot()
        self._root = None
        self._cache: dict = {}

        if torch_checkpoint and os.path.exists(torch_checkpoint) and HAS_TORCH:
            self.net = load_net(torch_checkpoint)
            self.has_checkpoint = True
            self.engine = "torch-mcts"
            self.device = getattr(self.net, "device", "cuda")
        elif checkpoint and os.path.exists(checkpoint):
            self.net = load_net(checkpoint)
            self.has_checkpoint = True
            self.engine = "numpy-mcts"
            self.device = "CPU"

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

    def _search(self, board: chess.Board, level: int, remember: bool):
        level = max(1, min(5, int(level)))
        if not self.has_checkpoint:
            return None, self.baseline.choose_move(board, level)
        cache = self._cache if remember else {}
        root_hint = self._reusable_root(board) if remember else None
        try:
            root, _, _ = mcts_search(
                board, self.net,
                simulations=SIMS.get(level, 40),
                temperature=0.0,
                rng=np.random.default_rng(),
                noise_eps=0.0,
                cache=cache,
                root=root_hint,
            )
            mv = best_move(root)
            if mv is None or not board.is_legal(mv):
                raise ValueError("kein legaler MCTS-Zug")
            if remember:
                chosen = next((c for c in root.children if c.move == mv), None)
                self._root = chosen
                if len(self._cache) > CACHE_LIMIT:
                    self._cache.clear()
            return root, mv
        except Exception:
            return None, self.baseline.choose_move(board, level)

    def choose_move(self, board: chess.Board, level: int = 3):
        _, mv = self._search(board, level, remember=True)
        return mv

    def hint(self, board: chess.Board, level: int = 3):
        _, mv = self._search(board, level, remember=False)
        return mv
