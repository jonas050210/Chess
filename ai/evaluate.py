"""Arena: MCTS-Checkpoint gegen Negamax-Baseline, alternierende Farben."""
from __future__ import annotations

import argparse
import os
import sys
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
        mv = best_move(root)
        return mv if mv and board.is_legal(mv) else next(iter(board.legal_moves), None)


class BaselineAgent:
    def __init__(self, level: int = 2):
        self.bot = BaselineBot()
        self.level = level

    def __call__(self, board: chess.Board):
        return self.bot.choose_move(board, self.level)


def play_game(white, black, max_plies: int = 200):
    board = chess.Board()
    for _ in range(max_plies):
        if board.is_game_over(claim_draw=True):
            break
        mv = white(board) if board.turn == chess.WHITE else black(board)
        if mv is None or not board.is_legal(mv):
            break
        board.push(mv)
    outcome = board.outcome(claim_draw=True)
    return outcome.winner if outcome else None


def evaluate_vs_baseline(net, games: int = 8, sims: int = 25,
                         level: int = 2, max_plies: int = 160) -> dict:
    mcts = MCTSAgent(net, sims)
    base = BaselineAgent(level)
    res = {"win": 0, "draw": 0, "loss": 0}
    for g in range(games):
        if g % 2 == 0:
            winner = play_game(mcts, base, max_plies)
            if winner is chess.WHITE:
                res["win"] += 1
            elif winner is chess.BLACK:
                res["loss"] += 1
            else:
                res["draw"] += 1
        else:
            winner = play_game(base, mcts, max_plies)
            if winner is chess.BLACK:
                res["win"] += 1
            elif winner is chess.WHITE:
                res["loss"] += 1
            else:
                res["draw"] += 1
    n = max(1, games)
    res["score"] = round((res["win"] + 0.5 * res["draw"]) / n, 3)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=os.path.join(ROOT, "checkpoints", "model.npz"))
    ap.add_argument("--torch-ckpt", default=None)
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--sims", type=int, default=25)
    ap.add_argument("--level", type=int, default=2)
    args = ap.parse_args()
    path = args.torch_ckpt or args.ckpt
    net = load_net(path if os.path.exists(path) else None)
    r = evaluate_vs_baseline(net, games=args.games, sims=args.sims, level=args.level)
    print(f"checkpoint={path if os.path.exists(path) else 'random'}")
    print(f"MCTS vs Baseline(level {args.level}): +{r['win']} ={r['draw']} -{r['loss']} | score={r['score']}")


if __name__ == "__main__":
    main()
