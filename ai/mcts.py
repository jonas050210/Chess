"""PUCT-MCTS mit Inference-Cache, Root-Reuse und Legal-Mask."""
from __future__ import annotations

import numpy as np
import chess
from chess.polyglot import zobrist_hash

from .env import board_to_tensor, legal_mask, legal_moves_with_indices, game_result


def position_key(board: chess.Board) -> tuple[int, int, int, bool]:
    """Key by position plus the history-dependent counters used in the network input."""
    return (zobrist_hash(board), min(board.halfmove_clock, 100),
            min(board.fullmove_number, 100), board.can_claim_threefold_repetition())


class Node:
    __slots__ = ("board", "parent", "move", "index", "prior", "children", "N", "W")

    def __init__(self, board: chess.Board, parent, move, index: int, prior: float):
        self.board = board
        self.parent = parent
        self.move = move
        self.index = index
        self.prior = prior
        self.children: list[Node] = []
        self.N = 0
        self.W = 0.0

    def q(self) -> float:
        return self.W / self.N if self.N else 0.0


def expand(node: Node, net, cache: dict | None = None, rng=None,
           noise_eps: float = 0.0, dirichlet_alpha: float = 0.3) -> float:
    pairs = legal_moves_with_indices(node.board)
    if not pairs:
        return 0.0
    key = position_key(node.board)
    if cache is not None and key in cache:
        probs_row, v = cache[key]
        probs = probs_row.reshape(1, -1)
    else:
        x = board_to_tensor(node.board).reshape(1, -1)
        m = legal_mask(node.board).reshape(1, -1)
        probs, value = net.forward(x, m)
        v = float(value[0])
        if cache is not None:
            cache[key] = (probs[0].copy(), v)

    priors = np.array([probs[0, i] for _, i in pairs], dtype=np.float64)
    if noise_eps > 0 and rng is not None:
        noise = rng.dirichlet([dirichlet_alpha] * len(pairs))
        priors = (1.0 - noise_eps) * priors + noise_eps * noise
    s = priors.sum()
    priors = priors / s if s > 0 else np.ones_like(priors) / len(pairs)

    for (mv, idx), p in zip(pairs, priors):
        cb = node.board.copy(stack=True)
        cb.push(mv)
        node.children.append(Node(cb, node, mv, idx, float(p)))
    return v


def select_child(node: Node, c_puct: float) -> Node:
    log_n = np.sqrt(max(1, node.N))
    best, best_score = None, -np.inf
    for child in node.children:
        q = -child.q()
        u = c_puct * child.prior * log_n / (1 + child.N)
        score = q + u
        if score > best_score:
            best, best_score = child, score
    return best


def visit_policy(root: Node, temperature: float) -> dict[int, float]:
    if not root.children:
        return {}
    visits = np.array([c.N for c in root.children], dtype=np.float64)
    if temperature <= 0 or visits.sum() == 0:
        probs = np.zeros_like(visits)
        probs[int(np.argmax(visits))] = 1.0
    else:
        probs = visits ** (1.0 / temperature)
        probs /= probs.sum()
    return {c.index: float(p) for c, p in zip(root.children, probs)}


def mcts_search(board: chess.Board, net, simulations: int = 40,
                c_puct: float = 1.5, temperature: float = 1.0,
                rng=None, noise_eps: float = 0.0,
                dirichlet_alpha: float = 0.3,
                cache: dict | None = None,
                root: Node | None = None):
    if cache is None:
        cache = {}
    reused = False
    if root is not None and position_key(root.board) == position_key(board):
        reused = True
        root.parent = None
        if not root.children:
            expand(root, net, cache=cache)
    else:
        root = Node(board.copy(stack=True), None, None, -1, 0.0)
        expand(root, net, cache=cache, rng=rng,
               noise_eps=noise_eps, dirichlet_alpha=dirichlet_alpha)

    for _ in range(max(1, int(simulations))):
        node = root
        path = [node]
        while node.children:
            node = select_child(node, c_puct)
            path.append(node)
        outcome = node.board.outcome(claim_draw=True)
        if outcome is not None:
            z = game_result(node.board, node.board.turn)
            v = 0.0 if z is None else float(z)
        else:
            v = expand(node, net, cache=cache)
        for n in reversed(path):
            n.N += 1
            n.W += v
            v = -v

    return root, visit_policy(root, temperature), root.children


def best_move(root: Node):
    if not root.children:
        return None
    return max(root.children, key=lambda c: c.N).move
