#!/usr/bin/env python3
"""Terminal-only supervised lessons. Never overwrites an active checkpoint.

This small curriculum teaches move priors, NOT overall chess strength. A held-
out score is reported; only the much stricter paired Arena gate can promote.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chess
import numpy as np

from ai.env import ACTION_SIZE, board_to_tensor, legal_mask, move_to_index
from ai.lessons import TRAIN, HOLDOUT, synthetic_lessons, verify_lessons
from ai.model import load_net
from ai.train_paths import candidate_output

ACTIVE = ROOT / "checkpoints" / "model.npz"
DEFAULT_OUT = ROOT / "checkpoints" / "candidates" / "basics.npz"


def _mirror_move(move: chess.Move) -> chess.Move:
    return chess.Move(chess.square_mirror(move.from_square),
                      chess.square_mirror(move.to_square), promotion=move.promotion)


def _flip_file(move: chess.Move) -> chess.Move:
    def reflect(square):
        return chess.square(7 - chess.square_file(square), chess.square_rank(square))
    return chess.Move(reflect(move.from_square), reflect(move.to_square),
                      promotion=move.promotion)


def examples(lessons, augment=False):
    """Color-mirror all lessons; file-reflect only positions without castling.

    Not reflecting castling rights avoids accidentally teaching illegal chess.
    Keep evaluation positions untouched: they are never used for gradients.
    """
    seen = set()
    for lesson in lessons:
        board, move = chess.Board(lesson.fen), chess.Move.from_uci(lesson.move)
        choices = (move.uci(),) + lesson.accepted
        variants = [(board, move, choices)]
        if augment:
            mirror = board.mirror()
            variants.append((mirror, _mirror_move(move), ()))
            if not board.castling_rights:
                reflected = board.transform(chess.flip_horizontal)
                variants.append((reflected, _flip_file(move), ()))
                variants.append((mirror.transform(chess.flip_horizontal),
                                 _flip_file(_mirror_move(move)), ()))
        for position, target, allowed in variants:
            if position.is_valid() and position.is_legal(target) and position.fen() not in seen:
                seen.add(position.fen())
                yield position, target, lesson.skill, allowed or (target.uci(),)


def rows(lessons, augment=False):
    states, masks, targets, skills, choices = [], [], [], [], []
    for board, move, skill, allowed in examples(lessons, augment):
        target = np.zeros(ACTION_SIZE, dtype=np.float32)
        target[move_to_index(move)] = 1.0
        states.append(board_to_tensor(board).ravel())
        masks.append(legal_mask(board))
        targets.append(target)
        skills.append(skill)
        choices.append({move_to_index(chess.Move.from_uci(uci)) for uci in allowed})
    return np.stack(states), np.stack(masks), np.stack(targets), skills, choices


def accuracy(net, dataset):
    states, masks, targets, skills, choices = dataset
    probabilities, _ = net.forward(states, masks)
    predicted = np.argmax(probabilities, axis=1)
    hits = np.array([int(prediction in allowed) for prediction, allowed
                     in zip(predicted, choices)])
    by_skill = {}
    for skill in sorted(set(skills)):
        indices = [i for i, name in enumerate(skills) if name == skill]
        by_skill[skill] = {"correct": int(hits[indices].sum()),
                           "total": len(indices)}
    return {"hits": int(hits.sum()), "total": len(hits),
            "accuracy": round(float(hits.mean()), 3),
            "target_probability": round(float(np.mean([
                probabilities[i, list(allowed)].sum() for i, allowed in enumerate(choices)])), 3),
            "by_skill": by_skill}


def main() -> int:
    parser = argparse.ArgumentParser(description="Train basic chess moves on a separate candidate")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--lr", type=float, default=.004)
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--examples-per-skill", type=int, default=48,
                        help="balanced samples per lesson type, per epoch")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-seconds", type=int, default=0)
    args = parser.parse_args()
    out = Path(candidate_output(parser, args.out, '.npz'))
    if (args.epochs < 1 or args.batch < 1 or args.examples_per_skill < 1 or
            args.max_seconds < 0 or not (0 < args.lr <= .1)):
        parser.error("epochs, batch and examples-per-skill must be positive; lr in (0, .1]")
    verify_lessons()
    generated = synthetic_lessons()
    training, holdout = rows(TRAIN + generated, augment=True), rows(HOLDOUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    net = load_net(str(out) if out.exists() else str(ACTIVE) if ACTIVE.exists() else None)
    before = accuracy(net, holdout)
    started = time.monotonic()
    rng = np.random.default_rng(args.seed)
    loss, completed = 0., 0
    by_skill = {skill: np.array([i for i, name in enumerate(training[3]) if name == skill])
                for skill in sorted(set(training[3]))}
    for epoch in range(args.epochs):
        if args.max_seconds and time.monotonic() - started >= args.max_seconds:
            break
        # Balance patterns: hundreds of easy hanging captures must not drown
        # out fewer mates, castles and opening examples.
        order = np.concatenate([rng.choice(indices, args.examples_per_skill,
                                            replace=len(indices) < args.examples_per_skill)
                                for indices in by_skill.values()])
        rng.shuffle(order)
        losses = []
        for offset in range(0, len(order), args.batch):
            if args.max_seconds and time.monotonic() - started >= args.max_seconds:
                break
            batch = order[offset:offset + args.batch]
            losses.append(net.train_batch(training[0][batch], training[1][batch],
                                          training[2][batch], np.zeros(len(batch), np.float32),
                                          lr=args.lr, value_weight=0.0))
        if not losses:
            break
        loss = float(np.mean(losses))
        completed = epoch + 1
        if completed % 10 == 0 or completed == 1:
            print(f"basics epoch {completed}/{args.epochs} policy_loss={loss:.3f}", flush=True)
    if completed:
        net.save(str(out))
    result = {"checkpoint": str(out), "epochs": completed, "loss": round(loss, 4),
              "training_examples": len(training[0]), "synthetic_positions": len(generated),
              "balanced_examples_per_skill": args.examples_per_skill,
              "train": accuracy(net, training), "holdout_before": before,
              "holdout_after": accuracy(net, holdout),
              "note": "Move-prior accuracy on a small held-out set is not playing strength."}
    out.with_suffix(".basics.json").write_text(json.dumps(result, indent=2))
    print("basics holdout:", result["holdout_before"]["hits"], "->",
          result["holdout_after"]["hits"], "/", len(HOLDOUT))
    print(f"basics candidate={out} report={out.with_suffix('.basics.json')}")
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
