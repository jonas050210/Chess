"""Negamax + Alpha-Beta + TT + Quiescence + Taktik-Bonus + Analyse-Modus."""
from __future__ import annotations

import random
import chess
from chess.polyglot import zobrist_hash

from .tactics import tactics_score

PIECE_VALUE = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000,
}
MATE = 1_000_000
INF = 10_000_000
LEVELS = {1: (1, 160), 2: (2, 70), 3: (3, 25), 4: (3, 8), 5: (4, 0)}


def _phase(board: chess.Board) -> str:
    npm = sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values()
              if p.piece_type not in (chess.PAWN, chess.KING))
    return "end" if npm < 2400 else "mid"


def _pst(piece_type: int, sq: int, color: bool, phase: str) -> int:
    r = chess.square_rank(sq) if color == chess.WHITE else 7 - chess.square_rank(sq)
    f = chess.square_file(sq)
    center = (3.5 - abs(r - 3.5)) + (3.5 - abs(f - 3.5))
    if piece_type == chess.PAWN:
        return int(center * 4 + r * (5 if phase == "end" else 3))
    if piece_type == chess.KNIGHT:
        return int(center * 12)
    if piece_type == chess.BISHOP:
        return int(center * 7)
    if piece_type == chess.ROOK:
        return int(r * 2 + center)
    if piece_type == chess.QUEEN:
        return int(center * 3)
    return int(center * 7) if phase == "end" else -int(center * 9)


def evaluate(board: chess.Board) -> int:
    phase = _phase(board)
    score = 0
    bishops = {"w": 0, "b": 0}
    pawn_files = {"w": [], "b": []}
    for sq, p in board.piece_map().items():
        val = PIECE_VALUE[p.piece_type] + _pst(p.piece_type, sq, p.color, phase)
        key = "w" if p.color == chess.WHITE else "b"
        score += val if key == "w" else -val
        if p.piece_type == chess.BISHOP:
            bishops[key] += 1
        if p.piece_type == chess.PAWN:
            pawn_files[key].append(chess.square_file(sq))
    if bishops["w"] >= 2:
        score += 35
    if bishops["b"] >= 2:
        score -= 35
    for key, sign in (("w", 1), ("b", -1)):
        files = pawn_files[key]
        for f in set(files):
            d = files.count(f) - 1
            if d > 0:
                score -= sign * d * 14
    score += 8 if board.turn == chess.WHITE else -8
    score += tactics_score(board)
    return score if board.turn == chess.WHITE else -score


def _ordered(board: chess.Board, tt_move=None, killers=None,
            captures_only: bool = False):
    if captures_only:
        moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
    else:
        moves = list(board.legal_moves)
    killers = killers or []
    def key(m: chess.Move):
        if tt_move is not None and m == tt_move:
            return -1_000_000
        s = 0
        if board.is_capture(m):
            victim = board.piece_type_at(m.to_square) or chess.PAWN
            attacker = board.piece_type_at(m.from_square)
            s += 1000 + PIECE_VALUE.get(victim, 0) * 10 - PIECE_VALUE.get(attacker, 0)
        if m.promotion:
            s += 900 + PIECE_VALUE.get(m.promotion, 0)
        if m in killers:
            s += 300
        if not captures_only:
            try:
                if board.gives_check(m):
                    s += 500
            except Exception:
                pass
        return -s
    moves.sort(key=key)
    return moves


class BaselineBot:
    def __init__(self):
        self.tt: dict = {}
        self.killers: dict[int, list] = {}
        self.nodes = 0

    def clear(self):
        self.tt.clear()
        self.killers.clear()

    def _quiescence(self, board, alpha, beta, ply, qdepth=4) -> int:
        self.nodes += 1
        stand = evaluate(board)
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        if qdepth <= 0:
            return alpha
        for m in _ordered(board, killers=self.killers.get(ply), captures_only=True):
            board.push(m)
            score = -self._quiescence(board, -beta, -alpha, ply + 1, qdepth - 1)
            board.pop()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _negamax(self, board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        key = zobrist_hash(board)
        orig_alpha, orig_beta = alpha, beta
        entry = self.tt.get(key)
        tt_move = entry.get("move") if entry else None
        if entry and entry["depth"] >= depth:
            s, flag = entry["score"], entry["flag"]
            if flag == "exact":
                return s
            if flag == "lower" and s > alpha:
                alpha = s
            if flag == "upper" and s < beta:
                beta = s
            if alpha >= beta:
                return s

        outcome = board.outcome(claim_draw=True)
        if outcome is not None:
            return 0 if outcome.winner is None else -MATE + ply
        if depth <= 0:
            return self._quiescence(board, alpha, beta, ply)

        best, best_move = -INF, None
        for m in _ordered(board, tt_move, self.killers.get(ply)):
            board.push(m)
            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score > best:
                best, best_move = score, m
            if best > alpha:
                alpha = best
            if alpha >= beta:
                if not board.is_capture(m):
                    ks = self.killers.setdefault(ply, [])
                    if m not in ks:
                        ks.insert(0, m)
                        del ks[2:]
                break

        flag = "upper" if best <= orig_alpha else ("lower" if best >= orig_beta else "exact")
        self.tt[key] = {"depth": depth, "score": best, "move": best_move, "flag": flag}
        if len(self.tt) > 50000:
            self.tt.clear()
        return best

    def _root(self, board, depth: int, jitter: int):
        key = zobrist_hash(board)
        entry = self.tt.get(key)
        rng = random.Random(key & 0xFFFFFFFF)
        best, best_move, alpha, beta = -INF, None, -INF, INF
        for m in _ordered(board, entry.get("move") if entry else None):
            board.push(m)
            score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            board.pop()
            score -= rng.randint(0, jitter)
            if score > best:
                best, best_move = score, m
            if best > alpha:
                alpha = best
        self.tt[key] = {"depth": depth, "score": best, "move": best_move, "flag": "exact"}
        return best_move

    def choose_move(self, board: chess.Board, level: int = 3):
        legal = list(board.legal_moves)
        if not legal:
            return None
        level = max(1, min(5, int(level)))
        depth, jitter = LEVELS[level]
        self.nodes = 0
        best = None
        for d in range(1, depth + 1):
            mv = self._root(board, d, jitter)
            if mv is not None:
                best = mv
        return best or legal[0]

    def hint(self, board: chess.Board, level: int = 3):
        return self.choose_move(board, level)

    def analyze(self, board: chess.Board, max_depth: int = 3, top_n: int = 3) -> dict:
        """Root-Scores + PV + Top-Züge für die Live-Analyse."""
        legal = list(board.legal_moves)
        self.nodes = 0
        if not legal:
            return {"best": None, "best_uci": None, "best_san": None,
                    "cp": 0, "pv": [], "top": [], "depth": 0, "nodes": 0}
        key = zobrist_hash(board)
        scored = []
        for d in range(1, max_depth + 1):
            scored, alpha, beta = [], -INF, INF
            tt_move = self.tt.get(key, {}).get("move")
            for m in _ordered(board, tt_move):
                board.push(m)
                score = -self._negamax(board, d - 1, -beta, -alpha, 1)
                board.pop()
                scored.append((score, m))
                if score > alpha:
                    alpha = score
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0][1]
            self.tt[key] = {"depth": d, "score": scored[0][0],
                            "move": best, "flag": "exact"}
            if len(self.tt) > 50000:
                self.tt.clear()

        pv, b = [], board.copy(stack=False)
        for _ in range(8):
            e = self.tt.get(zobrist_hash(b))
            mv = e.get("move") if e else None
            if mv is None or not b.is_legal(mv):
                break
            pv.append(b.san(mv))
            b.push(mv)

        top = [{"uci": m.uci(), "san": board.san(m), "cp": int(s)}
               for s, m in scored[:top_n]]
        best = scored[0][1]
        return {
            "best": best, "best_uci": best.uci(), "best_san": board.san(best),
            "cp": int(scored[0][0]), "pv": pv, "top": top,
            "depth": max_depth, "nodes": self.nodes,
        }
