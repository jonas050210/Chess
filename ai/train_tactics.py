"""Taktik-Distillation: Taktikpositionen -> Lehrer-Suche -> Policy/Value-Netz."""
from __future__ import annotations

import argparse
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import chess
import numpy as np

from ai.baseline import BaselineBot
from ai.env import ACTION_SIZE, board_to_tensor, legal_mask, move_to_index
from ai.model import load_net
from ai.tactics import detect_tactics

DEFAULT_CKPT = os.path.join(ROOT, "checkpoints", "model.npz")
CURATED_MATES = [
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8"),
    ("7k/6pp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8"),
    ("r5k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8"),
    ("6k1/5ppp/8/8/8/8/5PPP/1R4K1 w - - 0 1", "b1b8"),
]


def one_hot(move: chess.Move) -> np.ndarray | None:
    i = move_to_index(move)
    if i < 0:
        return None
    pi = np.zeros(ACTION_SIZE, dtype=np.float32)
    pi[i] = 1.0
    return pi


def policy_from_top(board: chess.Board, top: list[dict],
                    temperature: float = 200.0, smooth: float = 0.02) -> np.ndarray | None:
    if not top:
        return None
    scores = np.array([t["cp"] for t in top], dtype=np.float64)
    e = np.exp((scores - scores.max()) / max(1.0, temperature))
    e /= e.sum()
    pi = np.zeros(ACTION_SIZE, dtype=np.float32)
    for t, w in zip(top, e):
        try:
            m = chess.Move.from_uci(t["uci"])
        except Exception:
            continue
        i = move_to_index(m)
        if i >= 0:
            pi[i] += float(w)
    mask = legal_mask(board)
    n = mask.sum()
    if n > 0:
        pi += smooth * mask / n
    s = pi.sum()
    return pi / s if s > 0 else None


def random_positions(rng: random.Random, n: int):
    out = []
    for _ in range(n):
        b = chess.Board()
        for _ in range(rng.randint(8, 30)):
            if b.is_game_over(claim_draw=True):
                break
            b.push(rng.choice(list(b.legal_moves)))
        if not b.is_game_over(claim_draw=True):
            out.append(b)
    return out


def mate_positions(rng: random.Random, n: int, repeat: int, tries: int = 2500):
    out = []
    for fen, uci in CURATED_MATES:
        b = chess.Board(fen)
        m = chess.Move.from_uci(uci)
        if m in b.legal_moves:
            for _ in range(repeat):
                out.append((b.copy(stack=False), m, 1.0))
    for _ in range(tries):
        if len(out) >= n:
            break
        b = chess.Board()
        for _ in range(rng.randint(10, 28)):
            if b.is_game_over(claim_draw=True):
                break
            b.push(rng.choice(list(b.legal_moves)))
        if b.is_game_over(claim_draw=True):
            continue
        for m in list(b.legal_moves):
            b.push(m)
            mate = b.is_checkmate()
            b.pop()
            if mate:
                for _ in range(repeat):
                    out.append((b.copy(stack=False), m, 1.0))
                break
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", type=int, default=220)
    ap.add_argument("--mates", type=int, default=120)
    ap.add_argument("--mate-repeat", type=int, default=12)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--lr", type=float, default=0.02)
    ap.add_argument("--temperature", type=float, default=200.0)
    ap.add_argument("--smooth", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-seconds", type=int, default=0, help="0 = unbegrenzt")
    ap.add_argument("--target-loss", type=float, default=0.0, help="0 = aus")
    ap.add_argument("--patience", type=int, default=0, help="Early-Stopping, 0 = aus")
    ap.add_argument("--mate-check", action="store_true",
                    help="kuratierte Matt-in-1-Züge nach dem Training prüfen")
    ap.add_argument("--out", default=DEFAULT_CKPT)
    args = ap.parse_args()

    t0 = time.time()
    rng = random.Random(args.seed)
    teacher = BaselineBot()
    samples: list[tuple[chess.Board, np.ndarray, float]] = []

    # Kuratierte Matt-in-1-Stellungen mehrfach, damit das Netz sie sicher lernt.
    for b, m, z in mate_positions(rng, args.mates, args.mate_repeat):
        pi = one_hot(m)
        if pi is not None:
            samples.append((b, pi, z))
    teacher.clear()

    # Zufällige Stellungen mit mindestens einem Taktik-Tag: Lehrer gibt Zugverteilung.
    for b in random_positions(rng, args.positions):
        if not detect_tactics(b)["tags"]:
            continue
        teacher.clear()
        r = teacher.analyze(b, max_depth=args.depth, top_n=3)
        pi = policy_from_top(b, r["top"], args.temperature, args.smooth)
        if pi is None:
            continue
        z = float(np.tanh(r["cp"] / 400.0))
        samples.append((b, pi, z))

    if not samples:
        print("keine Taktikpositionen gefunden")
        return

    X, M, PI, Z = [], [], [], []
    for b, pi, z in samples:
        X.append(board_to_tensor(b).ravel())
        M.append(legal_mask(b))
        PI.append(pi)
        Z.append(z)
    X, M, PI = np.stack(X), np.stack(M), np.stack(PI)
    Z = np.array(Z, dtype=np.float32)

    net = load_net(args.out if os.path.exists(args.out) else None)
    best, bad, done = float("inf"), 0, 0
    for e in range(args.epochs):
        if args.max_seconds and time.time() - t0 > args.max_seconds:
            print("max-seconds erreicht, breche Epochen ab", flush=True)
            break
        idx = np.random.default_rng(args.seed + e).permutation(len(X))
        loss = net.train_batch(X[idx], M[idx], PI[idx], Z[idx], lr=args.lr)
        done = e + 1
        if (e + 1) % 5 == 0 or e == 0:
            print(f"epoch {e+1:>2}/{args.epochs} loss={loss:.4f} samples={len(X)}", flush=True)
        if loss < best - 1e-5:
            best, bad = loss, 0
        else:
            bad += 1
        if args.target_loss and loss <= args.target_loss:
            print(f"target-loss={args.target_loss} erreicht", flush=True)
            break
        if args.patience and bad >= args.patience:
            print(f"patience={args.patience} erreicht", flush=True)
            break
    net.save(args.out)
    print(f"checkpoint: {args.out} | epochen={done}/{args.epochs} | "
          f"loss={best:.4f} | taktik-positionen={len(X)} | "
          f"time={time.time()-t0:.1f}s")

    if args.mate_check:
        hits = 0
        for fen, uci in CURATED_MATES:
            b = chess.Board(fen)
            m = chess.Move.from_uci(uci)
            probs, _ = net.forward(board_to_tensor(b).ravel()[None],
                                   legal_mask(b)[None])
            mask = legal_mask(b)
            target = move_to_index(m)
            pred = int(np.argmax(probs[0] * mask))
            ok = target >= 0 and pred == target
            hits += int(ok)
            p = float(probs[0][target]) if target >= 0 else 0.0
            print(f"mate {uci}: {'OK' if ok else '—'} p={p:.3f}", flush=True)
        print(f"mate_hit={hits}/{len(CURATED_MATES)}", flush=True)


if __name__ == "__main__":
    main()
