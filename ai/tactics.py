"""Taktik-Erkennung + leichter Taktik-Bonus für die Bewertung."""
from __future__ import annotations

import chess

PIECE_VALUE = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000,
}
MAJOR = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)


def tactics_score(board: chess.Board) -> int:
    """Billiger, seitensichtiger Bonus für Suche/Quiescence."""
    score = 0
    if board.is_check():
        score += 12
    for sq, p in board.piece_map().items():
        if p.piece_type not in MAJOR:
            continue
        enemy = not p.color
        if board.is_attacked_by(enemy, sq) and not board.is_attacked_by(p.color, sq):
            v = PIECE_VALUE[p.piece_type] // 12
            score += -v if p.color == board.turn else v
    return score


def detect_tactics(board: chess.Board) -> dict:
    """Motiv-Tags für die Live-Analyse (außerhalb der Suche, daher darf es länger dauern)."""
    tags: list[str] = []
    details: dict = {}
    legal = list(board.legal_moves)

    if board.is_check():
        tags.append("Schach")
    if board.ep_square is not None:
        tags.append("En passant")
        details["ep"] = chess.square_name(board.ep_square)

    mate_moves, checks, forks = [], [], []
    captures = [m for m in legal if board.is_capture(m)]
    promos = [m for m in legal if m.promotion]

    for m in legal:
        try:
            if board.gives_check(m):
                checks.append(m.uci())
        except Exception:
            pass
        board.push(m)
        if board.is_checkmate():
            mate_moves.append(m.uci())
        pc = board.piece_at(m.to_square)
        if pc:
            attacked = board.attacks(m.to_square)
            targets = [s for s in attacked
                       if board.piece_at(s)
                       and board.piece_at(s).color != pc.color
                       and board.piece_at(s).piece_type in MAJOR]
            if len(set(targets)) >= 2:
                forks.append(m.uci())
        board.pop()

    if mate_moves:
        tags.append("Matt in 1")
        details["mate"] = mate_moves[:5]
    if checks:
        tags.append("Schachgebot")
        details["checks"] = checks[:6]
    if captures:
        tags.append("Schlag möglich")
        details["captures"] = len(captures)
    if promos:
        tags.append("Beförderung")
        details["promotions"] = len(promos)
    if forks:
        tags.append("Gabel möglich")
        details["forks"] = forks[:5]

    pins = []
    for sq, p in board.piece_map().items():
        if p.piece_type != chess.KING and board.is_pinned(p.color, sq):
            pins.append(chess.square_name(sq))
    if pins:
        tags.append("Fesselung")
        details["pins"] = pins[:8]

    hanging = []
    for sq, p in board.piece_map().items():
        if p.piece_type == chess.KING:
            continue
        if board.is_attacked_by(not p.color, sq) and not board.is_attacked_by(p.color, sq):
            hanging.append(chess.square_name(sq))
    if hanging:
        tags.append("Hängende Figur")
        details["hanging"] = hanging[:8]

    # stabile Reihenfolge, keine Duplikate
    seen, ordered = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return {"tags": ordered, "details": details}
