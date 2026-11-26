"""Dauerhafte Stellungsanalyse: Suche + Taktik-Motive + Metadaten."""
from __future__ import annotations

import chess
from chess.polyglot import zobrist_hash

from .baseline import BaselineBot
from .env import board_meta
from .tactics import detect_tactics


class AnalysisEngine:
    def __init__(self):
        self.bot = BaselineBot()
        self._key = None
        self._tactics = {"tags": [], "details": {}}

    def new_position(self, board: chess.Board):
        key = zobrist_hash(board)
        if key != self._key:
            self._key = key
            self.bot.clear()
            self._tactics = detect_tactics(board)

    def analyze(self, board: chess.Board, max_depth: int = 3) -> dict:
        self.new_position(board)
        r = self.bot.analyze(board, max_depth=max_depth)
        meta = board_meta(board)
        cp = r["cp"]
        return {
            "cp": cp,
            "eval_white": cp if board.turn == chess.WHITE else -cp,
            "best_uci": r["best_uci"],
            "best_san": r["best_san"],
            "pv": r["pv"],
            "top": r["top"],
            "depth": r["depth"],
            "nodes": r["nodes"],
            "tactics": self._tactics["tags"],
            "tactic_details": self._tactics["details"],
            "material": meta["material_balance"],
            "phase": meta["phase"],
            "legal_count": meta["legal_count"],
            "in_check": meta["in_check"],
        }
