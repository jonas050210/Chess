#!/usr/bin/env python3
"""Terminal-only training orchestrator with protected candidates and a real gate.

No browser endpoint invokes this file. An existing checkpoint is NEVER edited by
training: only a candidate that passes held-out lessons and paired completed
Arena games is atomically promoted and given a content-hash approval receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CKPT = ROOT / "checkpoints"
CANDIDATES = CKPT / "candidates"
ARCHIVE = CKPT / "archive"
ACTIVE_NPZ = CKPT / "model.npz"
ACTIVE_PT = CKPT / "model_torch.pt"

from ai.model import HAS_TORCH  # noqa: E402


def detect_device(requested: str) -> tuple[str, bool]:
    cuda = False
    if HAS_TORCH:
        import torch
        cuda = bool(torch.cuda.is_available())
    if requested == "auto":
        return ("cuda" if cuda else "cpu"), cuda
    if requested == "cuda" and not cuda:
        print("CUDA not found; using CPU", flush=True)
        return "cpu", False
    return requested, cuda


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Terminal-only chess training: lessons + candidates + paired Arena gate",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--preset", choices=["auto", "cpu", "basics", "smoke",
                                             "tactics", "gpu", "eval"], default="auto")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-seconds", type=int, default=0, help="0 = no wall-clock budget")
    parser.add_argument("--dry-run", action="store_true", help="print plan without writing files")
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--strict", action="store_true", help="stop at first failed step")
    parser.add_argument("--basics-epochs", type=int, default=80)
    parser.add_argument("--basics-lr", type=float, default=.004)
    parser.add_argument("--basics-examples-per-skill", type=int, default=48)
    parser.add_argument("--smoke-games", type=int, default=3)
    parser.add_argument("--smoke-sims", type=int, default=16)
    parser.add_argument("--smoke-epochs", type=int, default=2)
    parser.add_argument("--smoke-lr", type=float, default=5e-4)
    parser.add_argument("--max-plies", type=int, default=80)
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--tactics-positions", type=int, default=220)
    parser.add_argument("--tactics-mates", type=int, default=120)
    parser.add_argument("--mate-repeat", type=int, default=12)
    parser.add_argument("--tactics-depth", type=int, default=2)
    parser.add_argument("--tactics-epochs", type=int, default=120)
    parser.add_argument("--tactics-lr", type=float, default=.02)
    parser.add_argument("--target-loss", type=float, default=0.0)
    parser.add_argument("--patience", type=int, default=0)
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--gpu-sims", type=int, default=40)
    parser.add_argument("--gpu-epochs", type=int, default=3)
    parser.add_argument("--gpu-lr", type=float, default=1e-3)
    parser.add_argument("--gpu-batch", type=int, default=256)
    parser.add_argument("--train-every", type=int, default=2)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--eval-games", type=int, default=32,
                        help="minimum 12 completed paired games for promotion")
    parser.add_argument("--eval-sims", type=int, default=25)
    parser.add_argument("--eval-seed", type=int, default=1701)
    parser.add_argument("--baseline-level", type=int, default=2)
    parser.add_argument("--min-score", type=float, default=.55)
    parser.add_argument("--min-delta", type=float, default=.05)
    parser.add_argument("--min-basics-accuracy", type=float, default=.5)
    parser.add_argument("--resume", help="existing start checkpoint of the same format")
    parser.add_argument("--out", help="NumPy candidate path (never an active checkpoint)")
    parser.add_argument("--report", help="JSON report path")
    return parser


def plan_steps(preset: str, has_torch: bool) -> list[str]:
    if preset == "eval":
        return []
    if preset in ("basics", "smoke", "tactics", "gpu"):
        return [preset] if preset != "gpu" or has_torch else []
    cpu = ["basics", "smoke", "tactics"]
    return cpu + (["gpu"] if has_torch and preset == "auto" else [])


def cmd_for(name: str, args: argparse.Namespace, npz: Path, pt: Path,
            device: str, remaining: int, resume_pt: Path | None) -> list[str]:
    py = sys.executable
    if name == "basics":
        return [py, "ai/train_basics.py", "--epochs", str(args.basics_epochs),
                "--lr", str(args.basics_lr), "--batch", str(args.batch),
                "--examples-per-skill", str(args.basics_examples_per_skill),
                "--seed", str(args.seed),
                "--max-seconds", str(remaining), "--out", str(npz)]
    if name == "smoke":
        return [py, "ai/train_smoke.py", "--games", str(args.smoke_games),
                "--sims", str(args.smoke_sims), "--max-plies", str(args.max_plies),
                "--epochs", str(args.smoke_epochs), "--batch", str(args.batch),
                "--lr", str(args.smoke_lr), "--seed", str(args.seed + 1),
                "--max-seconds", str(remaining), "--out", str(npz)]
    if name == "tactics":
        return [py, "ai/train_tactics.py", "--positions", str(args.tactics_positions),
                "--mates", str(args.tactics_mates), "--mate-repeat", str(args.mate_repeat),
                "--depth", str(args.tactics_depth), "--epochs", str(args.tactics_epochs),
                "--lr", str(args.tactics_lr), "--seed", str(args.seed + 2),
                "--max-seconds", str(remaining), "--target-loss", str(args.target_loss),
                "--patience", str(args.patience), "--mate-check", "--out", str(npz)]
    if name == "gpu":
        command = [py, "ai/train_gpu.py", "--games", str(args.games),
                   "--sims", str(args.gpu_sims), "--max-plies", str(args.max_plies),
                   "--epochs", str(args.gpu_epochs), "--train-every", str(args.train_every),
                   "--batch", str(args.gpu_batch), "--lr", str(args.gpu_lr),
                   "--seed", str(args.seed + 3), "--channels", str(args.channels),
                   "--blocks", str(args.blocks), "--device", device,
                   "--out", str(pt), "--save-every", str(args.save_every),
                   "--eval-every", str(args.eval_every),
                   "--eval-games", str(args.eval_games),
                   "--max-seconds", str(remaining)]
        if resume_pt:
            command += ["--resume", str(resume_pt)]
        return command
    raise ValueError(name)


def run_step(command: list[str], strict: bool, timeout: float | None = None) -> int:
    """Return the real exit code; in strict mode a failure immediately propagates."""
    print("\n$ " + " ".join(command), flush=True)
    try:
        return subprocess.run(command, cwd=ROOT, check=strict, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print("Step stopped at the time budget", flush=True)
        if strict:
            raise
        return 124
    except subprocess.CalledProcessError as error:
        print(f"Step failed rc={error.returncode}", flush=True)
        if strict:
            raise
        return error.returncode


def atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=dst.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copy2(src, temp)
        os.replace(temp, dst)
    finally:
        temp.unlink(missing_ok=True)


def approve_checkpoint(target: Path, gate: dict, run_id: str) -> Path:
    """Write the receipt *after* promotion; a crash leaves an unapproved model."""
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    receipt = target.with_suffix(".approved.json")
    fd, name = tempfile.mkstemp(prefix=".approval-", dir=receipt.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"sha256": digest.hexdigest(), "run_id": run_id,
                       "gate": gate}, handle, indent=2)
        os.replace(name, receipt)
    finally:
        Path(name).unlink(missing_ok=True)
    return receipt


def arena_score(path: Path | None, games: int, sims: int, level: int,
                seed: int = 7, deadline: float | None = None) -> dict:
    from ai.evaluate import evaluate_vs_baseline
    from ai.model import load_net
    name = str(path) if path and path.exists() else None
    result = evaluate_vs_baseline(load_net(name), games=games, sims=sims, level=level,
                                  seed=seed, deadline=deadline)
    result["checkpoint"] = name or "random"
    print(f"ARENA {result['checkpoint']}: +{result['win']} ={result['draw']} "
          f"-{result['loss']} unfinished={result['unfinished']} score={result['score']}", flush=True)
    return result


def paired_delta(candidate: dict, current: dict) -> tuple[float, float, int]:
    """Exclude unfinished games at either end of each *matching* opening pair."""
    differences = [float(a) - float(b) for a, b in zip(candidate.get("game_scores", []),
                                                         current.get("game_scores", []))
                   if a is not None and b is not None]
    count = len(differences)
    if count < 2:
        return 0.0, float("-inf"), count
    mean = sum(differences) / count
    # The paired gain is bounded in [-1, 1]. Hoeffding's one-sided 95% lower
    # bound does not collapse to an unjustified point estimate when every
    # sampled opening has the same result.
    margin = math.sqrt(2 * math.log(20) / count)
    return mean, mean - margin, count


def lesson_score(path: Path) -> dict:
    from ai.lessons import HOLDOUT
    from ai.model import load_net
    from ai.train_basics import rows, accuracy
    return accuracy(load_net(str(path)), rows(HOLDOUT))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if (args.max_seconds < 0 or args.eval_games < 1 or args.eval_sims < 1 or
            args.batch < 1 or args.basics_examples_per_skill < 1 or
            args.basics_epochs < 1 or args.baseline_level not in range(1, 6) or
            not 0 <= args.min_score <= 1 or not -1 <= args.min_delta <= 1 or
            not 0 <= args.min_basics_accuracy <= 1):
        parser.error("Invalid training budget, evaluation count, level or promotion threshold")
    start = time.monotonic()
    deadline = start + args.max_seconds if args.max_seconds else None
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    npz = Path(args.out).resolve() if args.out else CANDIDATES / f"{run_id}.npz"
    pt = npz.with_suffix(".pt")
    if npz.suffix != ".npz" or npz == ACTIVE_NPZ or pt.resolve() == ACTIVE_PT:
        parser.error("--out must be a candidate .npz path, not an active checkpoint")
    report_path = Path(args.report).resolve() if args.report else CANDIDATES / f"{run_id}.json"
    if (report_path.suffix != ".json" or report_path in
            (ACTIVE_NPZ.with_suffix(".approved.json"), ACTIVE_PT.with_suffix(".approved.json"))):
        parser.error("--report must be a JSON report, not a model approval receipt")
    resume = Path(args.resume).resolve() if args.resume else None
    if resume and (not resume.exists() or resume.suffix not in (".npz", ".pt")):
        parser.error("--resume must name an existing .npz or .pt checkpoint")
    device, cuda = detect_device(args.device)
    if args.preset == "gpu" and not HAS_TORCH:
        parser.error("GPU preset requires PyTorch; install requirements-gpu.txt")
    steps = plan_steps(args.preset, HAS_TORCH and (cuda or args.preset == "gpu"))
    if resume and (args.preset == "eval" or
                   (resume.suffix == ".npz" and not any(
                       s in steps for s in ("basics", "smoke", "tactics"))) or
                   (resume.suffix == ".pt" and "gpu" not in steps)):
        parser.error("--resume must match a checkpoint format trained by this preset")
    start_npz = resume if resume and resume.suffix == ".npz" else (
        ACTIVE_NPZ if ACTIVE_NPZ.exists() else None)
    resume_pt = resume if resume and resume.suffix == ".pt" else (
        ACTIVE_PT if ACTIVE_PT.exists() else None)

    def remaining() -> int:
        return 0 if deadline is None else max(0, math.ceil(deadline - time.monotonic()))

    commands = [cmd_for(step, args, npz, pt, device, remaining(), resume_pt)
                for step in steps]
    report: dict = {"run_id": run_id, "preset": args.preset, "device": device,
                    "torch": HAS_TORCH, "cuda": cuda, "dry_run": args.dry_run,
                    "max_seconds": args.max_seconds, "seed": args.seed,
                    "steps": [{"name": s, "cmd": c} for s, c in zip(steps, commands)],
                    "candidates": [], "promoted": False}
    print(f"== Chess training · terminal only ==\nrun={run_id} steps={steps or ['eval']} "
          f"device={device} budget={args.max_seconds or 'unlimited'}s", flush=True)
    if args.dry_run:
        for command in commands:
            print("$ " + " ".join(command))
        print("Dry run: no files written, no checkpoint changed")
        return 0

    CANDIDATES.mkdir(parents=True, exist_ok=True)
    npz.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def finish(reason: str, code: int = 0) -> int:
        report["reason"] = reason
        report["duration_s"] = round(time.monotonic() - start, 2)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{reason} · report={report_path}", flush=True)
        return code

    if any(step in steps for step in ("basics", "smoke", "tactics")) and not npz.exists():
        if start_npz:
            shutil.copy2(start_npz, npz)
            print(f"Starting candidate copied from {start_npz}", flush=True)

    executed = []
    for step, command in zip(steps, commands):
        if deadline is not None and remaining() <= 0:
            executed.append({"name": step, "cmd": command, "rc": None, "skipped": "budget"})
            continue
        if deadline is not None:
            index = command.index("--max-seconds") + 1
            command[index] = str(remaining())
        try:
            rc = run_step(command, strict=args.strict,
                          timeout=max(.1, deadline - time.monotonic()) if deadline else None)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            rc = error.returncode if isinstance(error, subprocess.CalledProcessError) else 124
            executed.append({"name": step, "cmd": command, "rc": rc, "skipped": None})
            report["steps"] = executed
            return finish(f"Strict mode: {step} failed (rc={rc}); no promotion", rc)
        executed.append({"name": step, "cmd": command, "rc": rc, "skipped": None})
    report["steps"] = executed
    successful = {item["name"] for item in executed if item["rc"] == 0}
    failed = any(item["rc"] not in (0, None) for item in executed)
    if deadline is not None and remaining() <= 0:
        return finish("Budget exhausted before Arena; no promotion", 124 if failed else 0)

    from ai.bot import approved_checkpoint
    active_pt = ACTIVE_PT if HAS_TORCH and approved_checkpoint(str(ACTIVE_PT)) else None
    active = active_pt or (ACTIVE_NPZ if ACTIVE_NPZ.exists() else None)
    print("\n-- Completed-game Arena gate --", flush=True)
    current = arena_score(active, args.eval_games, args.eval_sims, args.baseline_level,
                          seed=args.eval_seed, deadline=deadline)
    report["current"] = current
    if deadline is not None and remaining() <= 0:
        return finish("Budget exhausted during Arena; no promotion")

    trained: list[tuple[Path, dict]] = []
    if npz.exists() and successful.intersection({"basics", "smoke", "tactics"}):
        trained.append((npz, arena_score(npz, args.eval_games, args.eval_sims,
                                         args.baseline_level, seed=args.eval_seed,
                                         deadline=deadline)))
    if pt.exists() and "gpu" in successful and HAS_TORCH and (deadline is None or remaining() > 0):
        trained.append((pt, arena_score(pt, args.eval_games, args.eval_sims,
                                        args.baseline_level, seed=args.eval_seed,
                                        deadline=deadline)))
    for path, result in trained:
        result["basics_holdout"] = lesson_score(path)
        report["candidates"].append({"path": str(path), **result})

    if not trained:
        return finish("No successfully trained candidate; no promotion", 1 if failed else 0)
    if failed or (deadline is not None and remaining() <= 0):
        return finish("No promotion: failed step or time budget", 1 if failed else 0)

    best_path, best = max(trained, key=lambda item: item[1]["score_lower95"])
    delta, lower, count = paired_delta(best, current)
    gate = {"paired_games": count, "mean_delta": round(delta, 3),
            "delta_lower95": round(lower, 3) if count >= 2 else None,
            "candidate_score_lower95": best["score_lower95"],
            "basics_holdout": best["basics_holdout"],
            "min_games": 12, "min_score": args.min_score,
            "min_delta": args.min_delta, "min_basics_accuracy": args.min_basics_accuracy}
    report["gate"] = gate
    allowed = (count >= 12 and best["resolved_games"] >= 12 and
               best["score_lower95"] >= args.min_score and lower >= args.min_delta and
               best["basics_holdout"]["accuracy"] >= args.min_basics_accuracy and
               (best_path.suffix != ".npz" or not active_pt))
    gate["passed"] = allowed
    if args.no_promote:
        return finish(f"No promotion (--no-promote); candidate "
                      f"{'passed' if allowed else 'failed'} the gate")
    if not allowed:
        return finish("Candidate did not pass the completed-game/lesson gate; no promotion")

    target = ACTIVE_PT if best_path.suffix == ".pt" else ACTIVE_NPZ
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = ARCHIVE / f"{target.stem}-{run_id}{target.suffix}"
        atomic_copy(target, backup)
        print(f"Archived {backup}")
    atomic_copy(best_path, target)
    receipt = approve_checkpoint(target, gate, run_id)
    report["promoted"] = True
    report["active_after"] = str(target)
    return finish(f"Promoted {best_path} -> {target}; approved by {receipt}")


if __name__ == "__main__":
    raise SystemExit(main())
