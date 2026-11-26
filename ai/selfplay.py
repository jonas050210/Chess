"""Self-Play-Datengenerator + Replay-Buffer (rules-only, keine externen Daten)."""
from __future__ import annotations

import numpy as np

from .env import ACTION_SIZE, INPUT_DIM, ChessEnv, game_result
from .mcts import mcts_search


class ReplayBuffer:
    def __init__(self, capacity: int = 20000, rng=None):
        self.capacity = capacity
        self.rng = rng or np.random.default_rng()
        self.data: list[dict] = []

    def add_game(self, records: list[dict]):
        self.data.extend(records)
        if len(self.data) > self.capacity:
            self.data = self.data[-self.capacity:]

    def sample(self, batch: int):
        n = len(self.data)
        if n == 0:
            return (np.zeros((0, INPUT_DIM), dtype=np.float32),
                    np.zeros((0, ACTION_SIZE), dtype=np.float32),
                    np.zeros((0, ACTION_SIZE), dtype=np.float32),
                    np.zeros((0,), dtype=np.float32))
        batch = min(batch, n)
        idx = self.rng.choice(n, size=batch, replace=False)
        rows = [self.data[int(i)] for i in idx]
        return (
            np.stack([r["x"] for r in rows]).astype(np.float32),
            np.stack([r["mask"] for r in rows]).astype(np.float32),
            np.stack([r["pi"] for r in rows]).astype(np.float32),
            np.array([r["z"] for r in rows], dtype=np.float32),
        )


def play_selfplay_game(net, simulations: int = 20, max_plies: int = 80,
                       rng=None, noise_eps: float = 0.25,
                       temperature: float = 1.0, temperature_drop: int = 12):
    rng = rng or np.random.default_rng()
    env = ChessEnv()
    records: list[dict] = []
    ply = 0

    while not env.done and ply < max_plies:
        temp = temperature if ply < temperature_drop else 0.0
        _, policy, children = mcts_search(
            env.board, net, simulations=simulations,
            temperature=temp, rng=rng, noise_eps=noise_eps,
        )
        target = np.zeros(ACTION_SIZE, dtype=np.float32)
        for idx, p in policy.items():
            target[idx] = p

        records.append({
            "x": env.tensor().ravel().copy(),
            "mask": env.mask().copy(),
            "pi": target,
            "to_play": env.board.turn,
        })

        if temp <= 0 or not children:
            mv = max(children, key=lambda c: c.N).move if children else None
        else:
            probs = np.array([policy.get(c.index, 0.0) for c in children], dtype=np.float64)
            if probs.sum() <= 0:
                probs = np.ones_like(probs) / len(probs)
            else:
                probs /= probs.sum()
            mv = children[int(rng.choice(len(children), p=probs))].move
        if mv is None:
            break
        env.step(mv)
        ply += 1

    outcome = env.board.outcome(claim_draw=False)
    if outcome is None:
        # A training ply cap is not a drawn game. Bootstrap the value from the
        # unfinished position; keep the flag for reporting/weighting later.
        if list(env.board.legal_moves):
            _, value = net.forward(env.tensor().ravel()[None], env.mask()[None])
            estimate = float(value[0])
        else:
            estimate = 0.0
        for r in records:
            r["z"] = estimate if r["to_play"] == env.board.turn else -estimate
            r["truncated"] = True
    elif outcome.winner is None:
        for r in records:
            r["z"] = 0.0
            r["truncated"] = False
    else:
        for r in records:
            r["z"] = 1.0 if r["to_play"] == outcome.winner else -1.0
            r["truncated"] = False
    return records
