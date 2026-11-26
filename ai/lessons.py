"""Small, inspectable chess fundamentals curriculum for terminal training.

Held-out examples are never fed to the trainer. They test *generalization*,
not playing strength; the paired Arena gate remains mandatory for promotion.
All examples are legal positions with an explicit human-chosen teaching move.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess


@dataclass(frozen=True)
class Lesson:
    fen: str
    move: str
    skill: str
    explanation: str
    # A held-out opening can have several sound moves. Training still uses the
    # single teaching move, but evaluation must not reject other good choices.
    accepted: tuple[str, ...] = ()


TRAIN = (
    Lesson("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8", "mate",
           "Look for a checkmate on the back rank."),
    Lesson("6k1/5ppp/8/8/8/8/5PPP/1R4K1 w - - 0 1", "b1b8", "mate",
           "A rook can deliver mate on the eighth rank."),
    Lesson("4k3/8/8/8/3q4/5N2/8/4K3 w - - 0 1", "f3d4", "capture",
           "Take an undefended queen with your knight."),
    Lesson("4k3/8/8/8/3r4/8/3R4/4K3 w - - 0 1", "d2d4", "capture",
           "Capture a hanging rook instead of moving away."),
    Lesson("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q", "promotion",
           "Promote a pawn on the last rank."),
    Lesson("4k3/8/8/8/8/8/p7/4K3 b - - 0 1", "a2a1q", "promotion",
           "Black can promote too."),
    Lesson("r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
           "e1g1", "king_safety", "Castle to put your king behind pawns."),
    Lesson("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
           "g1f3", "development", "Develop a knight and attack the center."),
    Lesson("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
           "g8f6", "development", "Develop your knight toward the center."),
    Lesson("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
           "e5d6", "en_passant", "Capture an otherwise safe pawn en passant."),
    Lesson("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
           "e2e4", "opening", "Occupy the center and open lines for your pieces."),
)

HOLDOUT = (
    Lesson("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2",
           "d8h4", "mate", "The exposed white king can be mated immediately."),
    Lesson("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
           "h5f7", "mate", "A queen and bishop coordinate on f7."),
    Lesson("6k1/8/5n2/8/4Q3/8/8/4K3 b - - 0 1", "f6e4", "capture",
           "Notice that the knight can win the queen."),
    Lesson("4k3/2r5/8/2R5/8/8/8/4K3 b - - 0 1", "c7c5", "capture",
           "Take the undefended rook."),
    Lesson("6k1/8/8/8/8/8/2p5/7K b - - 0 1", "c2c1q", "promotion",
           "Promote on a different file."),
    Lesson("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 2 5",
           "e8g8", "king_safety", "Castle the black king to safety."),
    Lesson("rnbqkbnr/ppp2ppp/4p3/3p4/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3",
           "g1f3", "development", "Develop before moving the same pawn again.",
           accepted=("g1f3", "b1c3", "b1d2")),
    Lesson("k7/8/8/6pP/8/5K2/8/8 w - g6 0 1",
           "h5g6", "en_passant", "Spot a safe en passant on another file."),
)


def synthetic_lessons() -> tuple[Lesson, ...]:
    """Generate inspectable, legal fundamentals from simple piece placements.

    Unlike random self-play, the desired move is mechanically checkable: win a
    hanging piece, promote, or make an actual en-passant capture. The final
    eight evaluation boards are explicitly excluded. These are lessons in
    patterns, not a set of invented 'best moves' in complex positions.
    """
    out: list[Lesson] = []
    seen = {lesson.fen for lesson in HOLDOUT} | {lesson.fen for lesson in TRAIN}
    kings = [(chess.A1, chess.H8), (chess.H1, chess.A8),
             (chess.C1, chess.G8)]

    def board_with_kings(white: int, black: int) -> chess.Board:
        board = chess.Board(None)
        board.set_piece_at(white, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(black, chess.Piece(chess.KING, chess.BLACK))
        board.turn = chess.WHITE
        return board

    def add(board: chess.Board, move: chess.Move, skill: str):
        if not board.is_valid() or board.is_game_over(claim_draw=False) or not board.is_legal(move):
            return
        if skill == "capture" and not board.is_capture(move):
            return
        if skill == "en_passant" and not board.is_en_passant(move):
            return
        if skill == "promotion" and move.promotion != chess.QUEEN:
            return
        fen = board.fen()
        if fen in seen:
            return
        seen.add(fen)
        out.append(Lesson(fen, move.uci(), skill, "Find the useful move before the opponent can respond."))

    for white_king, black_king in kings:
        # A winning capture is supported by real legal moves, not pseudo-moves.
        for square_name in ("b2", "c3", "d3", "e3", "f3", "g2", "d4", "e4"):
            origin = chess.parse_square(square_name)
            knight = board_with_kings(white_king, black_king)
            knight.set_piece_at(origin, chess.Piece(chess.KNIGHT, chess.WHITE))
            for target in list(knight.attacks(origin))[:5]:
                board = knight.copy(stack=False)
                board.set_piece_at(target, chess.Piece(chess.QUEEN, chess.BLACK))
                if chess.square_distance(target, black_king) > 1:
                    add(board, chess.Move(origin, target), "capture")
        for file in range(8):
            promotion = board_with_kings(white_king, black_king)
            start, dest = chess.square(file, 6), chess.square(file, 7)
            promotion.set_piece_at(start, chess.Piece(chess.PAWN, chess.WHITE))
            add(promotion, chess.Move(start, dest, chess.QUEEN), "promotion")
            for rank in (1, 2):
                rook = board_with_kings(white_king, black_king)
                source, target = chess.square(file, rank), chess.square(file, rank + 3)
                rook.set_piece_at(source, chess.Piece(chess.ROOK, chess.WHITE))
                rook.set_piece_at(target, chess.Piece(chess.ROOK, chess.BLACK))
                if chess.square_distance(target, black_king) > 1:
                    add(rook, chess.Move(source, target), "capture")
        for pawn_file in range(8):
            for other_file in (pawn_file - 1, pawn_file + 1):
                if not 0 <= other_file <= 7:
                    continue
                ep = board_with_kings(white_king, black_king)
                ep.set_piece_at(chess.square(pawn_file, 4), chess.Piece(chess.PAWN, chess.WHITE))
                ep.set_piece_at(chess.square(other_file, 4), chess.Piece(chess.PAWN, chess.BLACK))
                ep.ep_square = chess.square(other_file, 5)
                add(ep, chess.Move(chess.square(pawn_file, 4), ep.ep_square), "en_passant")
    return tuple(out)


def verify_lessons():
    for lesson in TRAIN + HOLDOUT:
        board = chess.Board(lesson.fen)
        move = chess.Move.from_uci(lesson.move)
        if not board.is_valid() or not board.is_legal(move):
            raise ValueError(f"Invalid {lesson.skill} lesson: {lesson.fen} {lesson.move}")
        if any(not board.is_legal(chess.Move.from_uci(uci)) for uci in lesson.accepted):
            raise ValueError(f"Invalid accepted move in {lesson.skill} lesson")
        if lesson.skill == "en_passant" and not board.is_en_passant(move):
            raise ValueError("En passant lesson must be a real en passant capture")
        if lesson.skill == "capture" and not board.is_capture(move):
            raise ValueError("Capture lesson must be a capture")
        if lesson.skill == "promotion" and move.promotion != chess.QUEEN:
            raise ValueError("Promotion lesson must promote a pawn to queen")
        if lesson.skill == "king_safety" and not board.is_castling(move):
            raise ValueError("King safety lesson must demonstrate castling")
        if lesson.skill == "mate":
            board.push(move)
            if not board.is_checkmate():
                raise ValueError(f"Lesson is not mate: {lesson.move}")
