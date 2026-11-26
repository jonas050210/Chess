"""Python-chess -> 21x8x8-Tensor + AlphaZero-artiger 8x8x73 Aktionsraum + Regel-Metadaten."""
from __future__ import annotations

import numpy as np
import chess

PLANES = 21                 # 12 Figuren + 9 Kontext-Ebenen
INPUT_DIM = PLANES * 8 * 8  # 1344
ACTION_SIZE = 8 * 8 * 73    # 4672
PLANES_PER_SQUARE = 73

PIECE_TO_PLANE = {
    "P": 0, "N": 1, "B": 2, "R": 3, "Q": 4, "K": 5,
    "p": 6, "n": 7, "b": 8, "r": 9, "q": 10, "k": 11,
}
PIECE_VALUE = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

DIRECTIONS = [
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
]
KNIGHT_DELTAS = [
    (2, 1), (1, 2), (-1, 2), (-2, 1),
    (-2, -1), (-1, -2), (1, -2), (2, -1),
]
UNDERPROMO = {chess.KNIGHT: 0, chess.BISHOP: 1, chess.ROOK: 2}


def board_to_tensor(board: chess.Board) -> np.ndarray:
    """(21, 8, 8) float32; Zeile 0 = Rank 8. Value-Netz sieht mehr als nur Figuren."""
    t = np.zeros((PLANES, 8, 8), dtype=np.float32)
    for sq, piece in board.piece_map().items():
        row = 7 - chess.square_rank(sq)
        col = chess.square_file(sq)
        t[PIECE_TO_PLANE[piece.symbol()], row, col] = 1.0

    # 12: Seite am Zug
    if board.turn == chess.WHITE:
        t[12, :, :] = 1.0
    # 13..16: Rochaderechte
    cr = board.castling_rights
    t[13, :, :] = float(bool(cr & chess.BB_H1))
    t[14, :, :] = float(bool(cr & chess.BB_A1))
    t[15, :, :] = float(bool(cr & chess.BB_H8))
    t[16, :, :] = float(bool(cr & chess.BB_A8))
    # 17: En-passant-Ziel
    if board.ep_square is not None:
        t[17, 7 - chess.square_rank(board.ep_square), chess.square_file(board.ep_square)] = 1.0
    # 18: 50-Züge-Zähler, 19: Zugnummer, 20: Wiederholungs-Druck
    t[18, :, :] = min(board.halfmove_clock / 100.0, 1.0)
    t[19, :, :] = min(board.fullmove_number / 100.0, 1.0)
    try:
        t[20, :, :] = float(board.can_claim_threefold_repetition())
    except Exception:
        t[20, :, :] = 0.0
    return t


def board_meta(board: chess.Board) -> dict:
    """Alles, was die UI über Regeln/Stellung wissen muss."""
    pieces = list(board.piece_map().values())
    balance = 0.0
    non_pawn = 0.0
    for p in pieces:
        v = PIECE_VALUE[p.piece_type]
        balance += v if p.color == chess.WHITE else -v
        if p.piece_type not in (chess.PAWN, chess.KING):
            non_pawn += v
    if board.fullmove_number <= 12 and non_pawn >= 55:
        phase = "Eröffnung"
    elif non_pawn >= 24:
        phase = "Mittelspiel"
    else:
        phase = "Endspiel"
    return {
        "castling": board.castling_xfen() or "-",
        "ep_square": chess.square_name(board.ep_square) if board.ep_square is not None else None,
        "halfmove_clock": board.halfmove_clock,
        "fullmove_number": board.fullmove_number,
        "legal_count": board.legal_moves.count(),
        "in_check": board.is_check(),
        "can_claim_threefold": bool(board.can_claim_threefold_repetition()),
        "can_claim_fifty": bool(board.can_claim_fifty_moves()),
        "insufficient_material": bool(board.is_insufficient_material()),
        "repetition_2": bool(board.is_repetition(2)),
        "material_balance": round(balance, 1),
        "phase": phase,
    }


def move_to_index(move: chess.Move) -> int:
    if move.null():
        return -1
    frm, to = move.from_square, move.to_square
    r0, f0 = chess.square_rank(frm), chess.square_file(frm)
    r1, f1 = chess.square_rank(to), chess.square_file(to)
    dr, df = r1 - r0, f1 - f0

    if move.promotion and move.promotion != chess.QUEEN:
        pidx = UNDERPROMO.get(move.promotion)
        if pidx is None:
            return -1
        dcat = 0 if df < 0 else (1 if df == 0 else 2)
        return frm * PLANES_PER_SQUARE + 64 + pidx * 3 + dcat

    if (dr, df) in KNIGHT_DELTAS:
        plane = 56 + KNIGHT_DELTAS.index((dr, df))
        return frm * PLANES_PER_SQUARE + plane

    for di, (ddr, ddf) in enumerate(DIRECTIONS):
        if ddr == 0:
            if dr != 0 or df == 0 or df % ddf != 0:
                continue
            k = df // ddf
        elif ddf == 0:
            if df != 0 or dr == 0 or dr % ddr != 0:
                continue
            k = dr // ddr
        else:
            if dr % ddr != 0 or df % ddf != 0:
                continue
            k1, k2 = dr // ddr, df // ddf
            if k1 != k2:
                continue
            k = k1
        if 1 <= k <= 7:
            plane = di * 7 + (k - 1)
            return frm * PLANES_PER_SQUARE + plane
    return -1


def legal_moves_with_indices(board: chess.Board) -> list[tuple[chess.Move, int]]:
    out = []
    for m in board.legal_moves:
        i = move_to_index(m)
        if i >= 0:
            out.append((m, i))
    out.sort(key=lambda x: x[1])
    return out


def legal_mask(board: chess.Board) -> np.ndarray:
    mask = np.zeros(ACTION_SIZE, dtype=np.float32)
    for _, i in legal_moves_with_indices(board):
        mask[i] = 1.0
    return mask


def game_result(board: chess.Board, perspective: bool) -> float | None:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    if outcome.winner is None:
        return 0.0
    return 1.0 if outcome.winner == perspective else -1.0


class ChessEnv:
    def __init__(self, fen: str | None = None):
        self.board = chess.Board(fen) if fen else chess.Board()

    def reset(self, fen: str | None = None) -> np.ndarray:
        self.board = chess.Board(fen) if fen else chess.Board()
        return self.tensor()

    def tensor(self) -> np.ndarray:
        return board_to_tensor(self.board)

    def mask(self) -> np.ndarray:
        return legal_mask(self.board)

    def legal(self) -> list[tuple[chess.Move, int]]:
        return legal_moves_with_indices(self.board)

    def meta(self) -> dict:
        return board_meta(self.board)

    def step(self, move: chess.Move):
        self.board.push(move)
        return self.tensor(), self.mask(), game_result(self.board, not self.board.turn)

    def copy(self) -> "ChessEnv":
        return ChessEnv(self.board.fen())

    @property
    def done(self) -> bool:
        return self.board.is_game_over(claim_draw=True)
