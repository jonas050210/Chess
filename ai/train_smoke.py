"""CPU-Smoke-Training: Self-Play -> mehrere Gradient-Steps -> NumPy-Checkpoint."""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from ai.model import load_net
from ai.selfplay import ReplayBuffer, play_selfplay_game
from ai.train_paths import candidate_output

DEFAULT_CKPT = os.path.join(ROOT, "checkpoints", "candidates", "smoke.npz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--sims", type=int, default=16)
    ap.add_argument("--max-plies", type=int, default=60)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-seconds", type=int, default=0, help="0 = unbegrenzt")
    ap.add_argument("--out", default=DEFAULT_CKPT)
    args = ap.parse_args()
    args.out = candidate_output(ap, args.out, '.npz')
    if args.games < 1 or args.sims < 1 or args.max_plies < 1 or args.epochs < 1 or args.batch < 1:
        ap.error("games, simulations, max plies, epochs and batch size must be positive")
    if not 0 < args.lr <= .1 or args.max_seconds < 0:
        ap.error("learning rate must be in (0, .1], max-seconds cannot be negative")

    t0 = time.time()
    rng = np.random.default_rng(args.seed)
    net = load_net(args.out if os.path.exists(args.out) else None)
    buf = ReplayBuffer(capacity=10000, rng=rng)
    total = 0
    played = 0
    for g in range(args.games):
        if args.max_seconds and time.time() - t0 > args.max_seconds:
            print("Time budget reached; stopping self-play", flush=True)
            break
        played = g + 1
        recs = play_selfplay_game(net, simulations=args.sims,
                                  max_plies=args.max_plies, rng=rng, noise_eps=0.20)
        buf.add_game(recs)
        total += len(recs)
        print(f"game {g+1}: {len(recs)} positions")

    losses = []
    if total == 0:
        print("No self-play samples; no checkpoint was written", flush=True)
        return 1
    for e in range(args.epochs):
        if args.max_seconds and time.time() - t0 >= args.max_seconds:
            print("Time budget exhausted before all epochs", flush=True)
            return 1
        x, m, pi, z = buf.sample(args.batch)
        losses.append(net.train_batch(x, m, pi, z, lr=args.lr))
        print(f"epoch {e+1}: loss={losses[-1]:.4f}", flush=True)
    net.save(args.out)
    print(f"checkpoint: {args.out} | games={played}/{args.games} | "
          f"samples={total} | batch={min(args.batch,total)} | "
          f"time={time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
