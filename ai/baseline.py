"""Small, deterministic chess engine for play, hints and training labels.

This is intentionally not presented as a grandmaster engine. It does, however,
search legal replies to checks, recognize mate at the horizon and respect a
per-move time budget so the web game stays responsive.
"""
from __future__ import annotations

import random
import time

import chess
from chess.polyglot import zobrist_hash

PIECE_VALUE = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 335,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0,
}
MATE = 1_000_000
INF = 10_000_000
# Depth, bounded positional jitter in centipawns, time budget in seconds.
LEVELS = {1: (1, 35, .18), 2: (2, 7, .45), 3: (3, 3, 1.1),
          4: (4, 0, 2.4), 5: (5, 0, 4.0)}


class SearchStopped(Exception):
    """The last completely searched iteration remains usable."""


def _phase(board: chess.Board) -> str:
    non_pawns = sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values()
                    if p.piece_type not in (chess.PAWN, chess.KING))
    return "end" if non_pawns < 2400 else "mid"


def _pst(piece_type: int, square: int, color: bool, phase: str) -> int:
    rank = chess.square_rank(square) if color else 7 - chess.square_rank(square)
    file = chess.square_file(square)
    center = (3.5 - abs(rank - 3.5)) + (3.5 - abs(file - 3.5))
    if piece_type == chess.PAWN:
        return int(center * 5 + rank * (10 if phase == "end" else 4))
    if piece_type == chess.KNIGHT:
        return int(center * 13 + (min(rank, 3) * 4 if phase == "mid" else 0))
    if piece_type == chess.BISHOP:
        return int(center * 7 + (min(rank, 3) * 3 if phase == "mid" else 0))
    if piece_type == chess.ROOK:
        return int(rank * 2 + center)
    if piece_type == chess.QUEEN:
        return int(center * 2)
    # Don't send the king into the middle until the endgame.
    return int(center * 10) if phase == "end" else -int(center * 9)


def evaluate(board: chess.Board) -> int:
    """Centipawns from the side-to-move's perspective."""
    phase = _phase(board)
    score = 0
    bishops = {chess.WHITE: 0, chess.BLACK: 0}
    pawns = {chess.WHITE: [], chess.BLACK: []}
    for square, piece in board.piece_map().items():
        value = PIECE_VALUE[piece.piece_type] + _pst(piece.piece_type, square,
                                                     piece.color, phase)
        score += value if piece.color else -value
        if piece.piece_type == chess.BISHOP:
            bishops[piece.color] += 1
        elif piece.piece_type == chess.PAWN:
            pawns[piece.color].append(square)
    for color, sign in ((chess.WHITE, 1), (chess.BLACK, -1)):
        if bishops[color] >= 2:
            score += sign * 30
        files = [chess.square_file(sq) for sq in pawns[color]]
        enemy = pawns[not color]
        for sq in pawns[color]:
            file = chess.square_file(sq)
            rank = chess.square_rank(sq) if color else 7 - chess.square_rank(sq)
            if files.count(file) > 1:
                score -= sign * 12  # doubled pawn
            if file - 1 not in files and file + 1 not in files:
                score -= sign * 10  # isolated pawn
            if not any(abs(file - chess.square_file(esq)) <= 1 and
                       (chess.square_rank(esq) > chess.square_rank(sq) if color
                        else chess.square_rank(esq) < chess.square_rank(sq))
                       for esq in enemy):
                score += sign * (14 + rank * 6)  # passed pawn
        king = board.king(color)
        if king is not None and phase == "mid":
            kfile, krank = chess.square_file(king), chess.square_rank(king)
            home = krank <= 1 if color else krank >= 6
            if home and kfile in (1, 2, 6, 7):
                score += sign * 22  # castled / tucked away
            # Reward a pawn shield; an exposed king is easy to attack.
            ahead = krank + (1 if color else -1)
            if 0 <= ahead <= 7:
                for file in range(max(0, kfile - 1), min(7, kfile + 1) + 1):
                    if board.piece_at(chess.square(file, ahead)) == chess.Piece(chess.PAWN, color):
                        score += sign * 7
    score += 8 if board.turn else -8  # tempo
    return score if board.turn else -score


def _ordered(board: chess.Board, tt_move=None, killers=None,
             captures_only: bool = False):
    moves = ([m for m in board.legal_moves if board.is_capture(m) or m.promotion]
             if captures_only else list(board.legal_moves))
    killers = killers or []

    def key(move: chess.Move):
        if move == tt_move:
            return -1_000_000
        s = 0
        if board.is_capture(move):
            victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant
            attacker = board.piece_type_at(move.from_square)
            s += 1000 + PIECE_VALUE[victim] * 10 - PIECE_VALUE.get(attacker, 0)
        if move.promotion:
            s += 900 + PIECE_VALUE[move.promotion]
        if move in killers:
            s += 300
        return -s

    moves.sort(key=key)
    return moves


def _tt_key(board: chess.Board) -> tuple[int, int, int]:
    # A Zobrist hash alone ignores 75-move and repetition state. Twofold,
    # threefold and fourfold histories must not share cached search scores:
    # the next recurrence can terminate a fivefold game in only one of them.
    repetition = (2 + int(board.is_repetition(3)) + int(board.is_repetition(4))
                  if board.is_repetition(2) else 0)
    return (zobrist_hash(board), min(board.halfmove_clock, 150), repetition)


def _mate_score(score: int, ply: int, store: bool) -> int:
    # TT entries can be reused at a different distance from the root.
    if score >= MATE - 10000:
        return score + ply if store else score - ply
    if score <= -MATE + 10000:
        return score - ply if store else score + ply
    return score


class BaselineBot:
    def __init__(self):
        self.tt: dict = {}
        self.killers: dict[int, list[chess.Move]] = {}
        self.nodes = 0
        self.deadline = float("inf")
        self.cancel = None

    def clear(self):
        self.tt.clear()
        self.killers.clear()

    def _check_stop(self):
        if self.nodes % 256 == 0 and (time.monotonic() >= self.deadline or
                                      (self.cancel and self.cancel())):
            raise SearchStopped()

    def _quiescence(self, board, alpha, beta, ply, qdepth=4) -> int:
        self.nodes += 1
        self._check_stop()
        outcome = board.outcome(claim_draw=False)
        if outcome is not None:
            return 0 if outcome.winner is None else -MATE + ply
        in_check = board.is_check()
        if not in_check:
            stand = evaluate(board)
            if stand >= beta:
                return beta
            alpha = max(alpha, stand)
            if qdepth <= 0:
                return alpha
        elif qdepth < -4:  # emergency bound for repeated checking lines
            return evaluate(board)
        # In check, stand-pat is illegal: search ALL evasions, even quiet ones.
        for move in _ordered(board, killers=self.killers.get(ply),
                             captures_only=not in_check):
            board.push(move)
            try:
                score = -self._quiescence(board, -beta, -alpha, ply + 1, qdepth - 1)
            finally:
                board.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    def _negamax(self, board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        self._check_stop()
        outcome = board.outcome(claim_draw=False)
        if outcome is not None:
            return 0 if outcome.winner is None else -MATE + ply
        if depth <= 0:
            return self._quiescence(board, alpha, beta, ply)

        key = _tt_key(board)
        orig_alpha, orig_beta = alpha, beta
        entry = self.tt.get(key)
        tt_move = entry.get("move") if entry else None
        if entry and entry["depth"] >= depth:
            value = _mate_score(entry["score"], ply, False)
            if entry["flag"] == "exact":
                return value
            if entry["flag"] == "lower":
                alpha = max(alpha, value)
            if entry["flag"] == "upper":
                beta = min(beta, value)
            if alpha >= beta:
                return value

        best, best_move = -INF, None
        for move in _ordered(board, tt_move, self.killers.get(ply)):
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.pop()
            if score > best:
                best, best_move = score, move
            alpha = max(alpha, best)
            if alpha >= beta:
                if not board.is_capture(move):
                    killers = self.killers.setdefault(ply, [])
                    if move not in killers:
                        killers.insert(0, move)
                        del killers[2:]
                break

        flag = "upper" if best <= orig_alpha else ("lower" if best >= orig_beta else "exact")
        self.tt[key] = {"depth": depth, "score": _mate_score(best, ply, True),
                        "move": best_move, "flag": flag}
        if len(self.tt) > 50000:
            self.tt.clear()
        return best

    def _root(self, board, depth: int, jitter: int):
        key = _tt_key(board)
        entry = self.tt.get(key)
        rng = random.Random(zobrist_hash(board) & 0xFFFFFFFF)
        best, best_move, alpha = -INF, None, -INF
        for move in _ordered(board, entry.get("move") if entry else None):
            self._check_stop()
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -INF, -alpha, 1)
            finally:
                board.pop()
            if abs(score) < MATE - 10000:
                score -= rng.randint(0, jitter)
            if score > best:
                best, best_move = score, move
            alpha = max(alpha, best)
        if best_move:
            self.tt[key] = {"depth": depth, "score": best, "move": best_move,
                            "flag": "exact"}
        return best_move

    def choose_move(self, board: chess.Board, level: int = 3,
                    time_limit: float | None = None, cancel=None):
        legal = list(board.legal_moves)
        if not legal:
            return None
        depth, jitter, budget = LEVELS[max(1, min(5, int(level)))]
        self.deadline = time.monotonic() + (budget if time_limit is None else time_limit)
        self.cancel = cancel
        self.nodes = 0
        best = legal[0]
        try:
            for iteration in range(1, depth + 1):
                move = self._root(board, iteration, jitter)
                if move is not None:
                    best = move
        except SearchStopped:
            pass
        finally:
            self.deadline = float("inf")
            self.cancel = None
        return best

    def hint(self, board: chess.Board, level: int = 3):
        return self.choose_move(board, level)

    def analyze(self, board: chess.Board, max_depth: int = 3, top_n: int = 3) -> dict:
        legal = list(board.legal_moves)
        self.nodes = 0
        if not legal:
            return {"best": None, "best_uci": None, "best_san": None,
                    "cp": 0, "pv": [], "top": [], "depth": 0, "nodes": 0}
        self.deadline = time.monotonic() + 3.0
        scored, finished_depth = [], 0
        try:
            for depth in range(1, max_depth + 1):
                trial, alpha = [], -INF
                entry = self.tt.get(_tt_key(board), {})
                for move in _ordered(board, entry.get("move")):
                    self._check_stop()
                    board.push(move)
                    try:
                        score = -self._negamax(board, depth - 1, -INF, -alpha, 1)
                    finally:
                        board.pop()
                    trial.append((score, move))
                    alpha = max(alpha, score)
                trial.sort(key=lambda pair: pair[0], reverse=True)
                scored, finished_depth = trial, depth
                self.tt[_tt_key(board)] = {"depth": depth, "score": scored[0][0],
                                            "move": scored[0][1], "flag": "exact"}
        except SearchStopped:
            pass
        finally:
            self.deadline = float("inf")
        if not scored:
            scored = [(evaluate(board), legal[0])]
        pv, current = [], board.copy(stack=True)
        for _ in range(8):
            entry = self.tt.get(_tt_key(current))
            move = entry.get("move") if entry else None
            if move is None or not current.is_legal(move):
                break
            pv.append(current.san(move))
            current.push(move)
        top = [{"uci": move.uci(), "san": board.san(move), "cp": int(score)}
               for score, move in scored[:top_n]]
        best = scored[0][1]
        return {"best": best, "best_uci": best.uci(), "best_san": board.san(best),
                "cp": int(scored[0][0]), "pv": pv, "top": top,
                "depth": finished_depth, "nodes": self.nodes}
