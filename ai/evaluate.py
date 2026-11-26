"""Reproducible paired Arena games; only completed games count as results.

An illegal move is a loss for the offending side. A ply or time limit is NOT
silently converted into a draw: unfinished games have a missing score and
cannot contribute to a checkpoint-promotion gate.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from dataclasses import dataclass

import chess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai.baseline import BaselineBot
from ai.mcts import mcts_search, best_move
from ai.model import load_net


class MCTSAgent:
    def __init__(self, net, simulations: int = 25):
        self.net = net
        self.sims = simulations

    def __call__(self, board: chess.Board):
        root, _, _ = mcts_search(board, self.net, simulations=self.sims, temperature=0.0)
        move = best_move(root)
        return move if move and board.is_legal(move) else None


class BaselineAgent:
    def __init__(self, level: int = 2):
        self.bot = BaselineBot()
        self.level = level

    def __call__(self, board: chess.Board):
        return self.bot.choose_move(board, self.level)


@dataclass(frozen=True)
class GameResult:
    winner: bool | None
    reason: str


def play_game(white, black, max_plies: int = 200,
              board: chess.Board | None = None, deadline: float | None = None) -> GameResult:
    position = board.copy(stack=True) if board is not None else chess.Board()
    for _ in range(max_plies):
        outcome = position.outcome(claim_draw=False)
        if outcome is not None:
            return GameResult(outcome.winner, outcome.termination.name.lower())
        if deadline is not None and time.monotonic() >= deadline:
            return GameResult(None, "time_limit")
        turn = position.turn
        move = white(position.copy(stack=True)) if turn == chess.WHITE else black(position.copy(stack=True))
        # A slow agent cannot start a fresh move after an elapsed wall-time cap.
        if deadline is not None and time.monotonic() >= deadline:
            return GameResult(None, "time_limit")
        if not isinstance(move, chess.Move) or not position.is_legal(move):
            return GameResult(not turn, "illegal_move")
        position.push(move)
    outcome = position.outcome(claim_draw=False)
    if outcome is not None:
        return GameResult(outcome.winner, outcome.termination.name.lower())
    return GameResult(None, "max_plies")


def score_bounds(scores: list[float]) -> tuple[float, float]:
    """Conservative one-sided 95% bounds for a mean game score in [0, 1]."""
    if not scores:
        return 0.0, 1.0
    mean = sum(scores) / len(scores)
    margin = math.sqrt(math.log(20) / (2 * len(scores)))
    return max(0.0, mean - margin), min(1.0, mean + margin)


def evaluate_vs_baseline(net, games: int = 8, sims: int = 25,
                         level: int = 2, max_plies: int = 160,
                         seed: int = 7, deadline: float | None = None) -> dict:
    """Same openings and color order for candidate/current on separate calls."""
    mcts = MCTSAgent(net, sims)
    base = BaselineAgent(level)
    rng = random.Random(seed)
    result = {"win": 0, "draw": 0, "loss": 0, "unfinished": 0,
              "illegal_moves": 0}
    scores: list[float | None] = []
    reasons: list[str] = []
    for game in range(games):
        if deadline is not None and time.monotonic() >= deadline:
            scores.extend([None] * (games - game))
            reasons.extend(["time_limit"] * (games - game))
            result["unfinished"] += games - game
            break
        opening = chess.Board()
        for _ in range(4 + 2 * rng.randrange(3)):
            if opening.is_game_over(claim_draw=False):
                break
            opening.push(rng.choice(list(opening.legal_moves)))
        candidate_white = game % 2 == 0
        played = play_game(mcts if candidate_white else base,
                           base if candidate_white else mcts,
                           max_plies, opening, deadline)
        reasons.append(played.reason)
        if played.reason in {"max_plies", "time_limit"}:
            result["unfinished"] += 1
            scores.append(None)
        elif played.winner is None:
            result["draw"] += 1
            scores.append(.5)
        elif played.winner == candidate_white:
            result["win"] += 1
            scores.append(1.)
        else:
            result["loss"] += 1
            scores.append(0.)
        if played.reason == "illegal_move":
            result["illegal_moves"] += 1
    finished = [score for score in scores if score is not None]
    count = len(finished)
    mean = sum(finished) / count if count else 0.0
    # A bounded one-sided 95% interval does not claim certainty at 12/12.
    lower, upper = score_bounds(finished)
    result.update(score=round(mean, 3),
                  score_lower95=lower, score_upper95=upper,
                  resolved_games=count, game_scores=scores, reasons=reasons)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", default=os.path.join(ROOT, "checkpoints", "model.npz"))
    parser.add_argument("--torch-ckpt", default=None)
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--sims", type=int, default=25)
    parser.add_argument("--level", type=int, default=2)
    args = parser.parse_args()
    path = args.torch_ckpt or args.ckpt
    net = load_net(path if os.path.exists(path) else None)
    result = evaluate_vs_baseline(net, games=args.games, sims=args.sims, level=args.level)
    print(f"checkpoint={path if os.path.exists(path) else 'random'}")
    print(f"MCTS vs search(level {args.level}): +{result['win']} ={result['draw']} "
          f"-{result['loss']} unfinished={result['unfinished']} score={result['score']}")


if __name__ == "__main__":
    main()
