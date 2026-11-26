#!/usr/bin/env python3
"""Terminal-Orchestrator für Training v6.

Grundregeln:
  * Training läuft AUSSCHLIESSLICH im Terminal (keine Buttons in Browser/Tk).
  * Bestehende `checkpoints/model.npz` / `model_torch.pt` werden nie direkt überschrieben.
  * Jeder Lauf schreibt Kandidaten nach `checkpoints/candidates/`.
  * Arena gegen Baseline + Gate entscheidet über Promotion; Archiv bei Ersatz.
  * Zeitbudget, Seeds, Early-Stopping und JSON-Report sind immer dabei.

Beispiele:
  python3 ai/train_cli.py --help
  python3 ai/train_cli.py --dry-run
  python3 ai/train_cli.py --preset cpu --max-seconds 300
  bash ubuntu/train.sh --preset auto --games 200 --eval-games 32
"""
from __future__ import annotations

import argparse
import json
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
        try:
            import torch
            cuda = bool(torch.cuda.is_available())
        except Exception:
            cuda = False
    if requested == "auto":
        return ("cuda" if cuda else "cpu"), cuda
    if requested == "cuda" and not cuda:
        print("WARN  CUDA angefordert, aber nicht verfügbar → cpu", flush=True)
        return "cpu", False
    return requested, cuda


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Chess-Training v6 · nur Terminal · Kandidaten + Arena-Gate",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--preset", choices=["auto", "cpu", "gpu", "smoke", "tactics", "eval"],
                    default="auto", help="auto=CPU + GPU falls vorhanden")
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-seconds", type=int, default=0, help="0 = unbegrenzt")
    ap.add_argument("--dry-run", action="store_true", help="nur Plan/Commands ausgeben")
    ap.add_argument("--no-promote", action="store_true", help="Kandidat nie aktivieren")
    ap.add_argument("--strict", action="store_true", help="bei Step-Fehler sofort abbrechen")

    # CPU-Smoke
    ap.add_argument("--smoke-games", type=int, default=3)
    ap.add_argument("--smoke-sims", type=int, default=16)
    ap.add_argument("--smoke-epochs", type=int, default=2)
    ap.add_argument("--smoke-lr", type=float, default=5e-4)
    ap.add_argument("--max-plies", type=int, default=60)
    ap.add_argument("--batch", type=int, default=128)

    # Taktik
    ap.add_argument("--tactics-positions", type=int, default=220)
    ap.add_argument("--tactics-mates", type=int, default=120)
    ap.add_argument("--mate-repeat", type=int, default=12)
    ap.add_argument("--tactics-depth", type=int, default=2)
    ap.add_argument("--tactics-epochs", type=int, default=120)
    ap.add_argument("--tactics-lr", type=float, default=0.02)
    ap.add_argument("--target-loss", type=float, default=0.0, help="0 = aus")
    ap.add_argument("--patience", type=int, default=0, help="0 = aus")

    # GPU-Selfplay
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--gpu-sims", type=int, default=40)
    ap.add_argument("--gpu-epochs", type=int, default=3)
    ap.add_argument("--gpu-lr", type=float, default=1e-3)
    ap.add_argument("--gpu-batch", type=int, default=256)
    ap.add_argument("--train-every", type=int, default=2)
    ap.add_argument("--save-every", type=int, default=10)
    ap.add_argument("--eval-every", type=int, default=10)
    ap.add_argument("--channels", type=int, default=64)
    ap.add_argument("--blocks", type=int, default=4)

    # Arena-Gate
    ap.add_argument("--eval-games", type=int, default=32,
                    help="paired Arena games; promotion requires at least 12")
    ap.add_argument("--eval-sims", type=int, default=25)
    ap.add_argument("--eval-seed", type=int, default=1701,
                    help="same reproducible opening set for active and candidate")
    ap.add_argument("--baseline-level", type=int, default=2)
    ap.add_argument("--min-score", type=float, default=0.55)
    ap.add_argument("--min-delta", type=float, default=0.05)

    ap.add_argument("--resume", default=None, help="Startcheckpoint statt aktivem Modell")
    ap.add_argument("--out", default=None, help="fester NumPy-Kandidatenpfad")
    ap.add_argument("--report", default=None, help="JSON-Reportpfad")
    return ap


def plan_steps(preset: str, has_torch: bool) -> list[str]:
    if preset == "eval":
        return []
    if preset == "smoke":
        return ["smoke"]
    if preset == "tactics":
        return ["tactics"]
    if preset == "gpu":
        return ["gpu"] if has_torch else []
    if preset == "cpu":
        return ["smoke", "tactics"]
    return ["smoke", "tactics"] + (["gpu"] if has_torch else [])


def cmd_for(name: str, a: argparse.Namespace, npz: Path, pt: Path,
            device: str, remaining: int, resume_pt: Path | None) -> list[str]:
    py = sys.executable
    if name == "smoke":
        return [py, "ai/train_smoke.py",
                "--games", str(a.smoke_games), "--sims", str(a.smoke_sims),
                "--max-plies", str(a.max_plies), "--epochs", str(a.smoke_epochs),
                "--batch", str(a.batch), "--lr", str(a.smoke_lr),
                "--seed", str(a.seed), "--max-seconds", str(remaining),
                "--out", str(npz)]
    if name == "tactics":
        return [py, "ai/train_tactics.py",
                "--positions", str(a.tactics_positions),
                "--mates", str(a.tactics_mates),
                "--mate-repeat", str(a.mate_repeat),
                "--depth", str(a.tactics_depth),
                "--epochs", str(a.tactics_epochs),
                "--lr", str(a.tactics_lr),
                "--seed", str(a.seed + 1),
                "--max-seconds", str(remaining),
                "--target-loss", str(a.target_loss),
                "--patience", str(a.patience),
                "--mate-check", "--out", str(npz)]
    if name == "gpu":
        c = [py, "ai/train_gpu.py",
             "--games", str(a.games), "--sims", str(a.gpu_sims),
             "--max-plies", str(a.max_plies), "--epochs", str(a.gpu_epochs),
             "--train-every", str(a.train_every), "--batch", str(a.gpu_batch),
             "--lr", str(a.gpu_lr), "--seed", str(a.seed + 2),
             "--channels", str(a.channels), "--blocks", str(a.blocks),
             "--device", device, "--out", str(pt),
             "--save-every", str(a.save_every),
             "--eval-every", str(a.eval_every),
             "--eval-games", str(a.eval_games),
             "--max-seconds", str(remaining)]
        if resume_pt and resume_pt.exists():
            c += ["--resume", str(resume_pt)]
        return c
    raise ValueError(name)


def run_step(cmd: list[str], strict: bool) -> int:
    print("\n$ " + " ".join(cmd), flush=True)
    try:
        return subprocess.run(cmd, cwd=ROOT, check=strict).returncode
    except subprocess.CalledProcessError as e:
        print(f"WARN  Step fehlgeschlagen rc={e.returncode}", flush=True)
        return e.returncode


def atomic_copy(src: Path, dst: Path) -> None:
    """Copy beside the destination, then atomically replace it on the same filesystem."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=dst.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def arena_score(path: Path | None, games: int, sims: int, level: int,
                seed: int = 7) -> dict:
    from ai.evaluate import evaluate_vs_baseline
    from ai.model import load_net
    p = str(path) if path and path.exists() else None
    net = load_net(p)
    r = evaluate_vs_baseline(net, games=games, sims=sims, level=level, seed=seed)
    r["checkpoint"] = p or "random"
    print(f"ARENA {r['checkpoint']}: +{r['win']} ={r['draw']} -{r['loss']} "
          f"score={r['score']}", flush=True)
    return r


def paired_delta(candidate: dict, current: dict) -> tuple[float, float, int]:
    """Return paired mean score gain, conservative 95% lower bound, sample count."""
    a = candidate.get("game_scores", [])
    b = current.get("game_scores", [])
    n = min(len(a), len(b))
    if n < 2:
        return 0.0, float("-inf"), n
    diffs = [float(a[i]) - float(b[i]) for i in range(n)]
    mean = sum(diffs) / n
    variance = sum((x - mean) ** 2 for x in diffs) / (n - 1)
    lower = mean - 1.96 * (variance / n) ** 0.5
    return mean, lower, n


def main() -> int:
    a = build_parser().parse_args()
    t0 = time.time()
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    npz = Path(a.out).resolve() if a.out else CANDIDATES / f"{run_id}.npz"
    pt = npz.with_suffix(".pt") if a.out else CANDIDATES / f"{run_id}.pt"
    npz.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(a.report).resolve() if a.report else CANDIDATES / f"{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    device, cuda = detect_device(a.device)
    steps = plan_steps(a.preset, HAS_TORCH)
    resume = Path(a.resume).resolve() if a.resume else None
    start_npz = resume if resume and resume.suffix == ".npz" else (
        ACTIVE_NPZ if ACTIVE_NPZ.exists() else None)
    resume_pt = resume if resume and resume.suffix == ".pt" else (
        ACTIVE_PT if ACTIVE_PT.exists() else None)

    print("== Chess-Training v6 · Terminal only ==")
    print(f"run={run_id} preset={a.preset} device={device} torch={HAS_TORCH} cuda={cuda}")
    if not HAS_TORCH and a.preset in ("auto", "gpu"):
        print("HINWEIS PyTorch fehlt → GPU-Selfplay wird übersprungen, CPU-Schritte laufen")
    print(f"candidate_npz={npz}")
    print(f"candidate_pt={pt}")
    print(f"steps={steps or ['nur Arena']} budget={a.max_seconds or '∞'}s")

    def remaining() -> int:
        if not a.max_seconds:
            return 0
        return max(0, int(a.max_seconds - (time.time() - t0)))

    commands = [cmd_for(s, a, npz, pt, device, remaining(), resume_pt) for s in steps]
    report: dict = {
        "run_id": run_id, "preset": a.preset, "device": device,
        "torch": HAS_TORCH, "cuda": cuda, "dry_run": a.dry_run,
        "max_seconds": a.max_seconds, "seed": a.seed,
        "steps": [{"name": s, "cmd": c} for s, c in zip(steps, commands)],
        "candidates": [], "promoted": False,
        "note": "Kurze Läufe beweisen keine Spielstärke; Gate schützt vor Regression.",
    }

    if a.dry_run:
        for c in commands:
            print("$ " + " ".join(c))
        print("DRY-RUN · keine Checkpoints verändert (nur Report)")
        report["duration_s"] = round(time.time() - t0, 2)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"report={report_path}")
        return 0

    # Aktives NumPy-Modell als Start kopieren → nie destruktiv trainieren.
    if any(s in steps for s in ("smoke", "tactics")) and not npz.exists():
        if start_npz and start_npz.exists():
            shutil.copy2(start_npz, npz)
            print(f"start={start_npz} → {npz}")
        else:
            print("start=random (kein NumPy-Checkpoint vorhanden)")

    executed = []
    for s, c in zip(steps, commands):
        if a.max_seconds and remaining() <= 0:
            print(f"SKIP  {s}: Zeitbudget aufgebraucht", flush=True)
            executed.append({"name": s, "cmd": c, "rc": None, "skipped": "budget"})
            continue
        # Bei begrenztem Budget das verbleibende Sekunden-Kontingent aktualisieren.
        if a.max_seconds:
            for i, x in enumerate(c):
                if x == "--max-seconds" and i + 1 < len(c):
                    c[i + 1] = str(remaining())
        rc = run_step(c, a.strict)
        executed.append({"name": s, "cmd": c, "rc": rc, "skipped": None})
    report["steps"] = executed

    # Arena: aktiver Checkpoint + alle trainierten Kandidaten.
    from ai.model import load_net  # noqa: F401  ( Konsistenz mit load_net )
    active_pt = ACTIVE_PT if ACTIVE_PT.exists() and HAS_TORCH else None
    active = active_pt or (ACTIVE_NPZ if ACTIVE_NPZ.exists() else None)
    print("\n-- Arena-Gate --", flush=True)
    current = arena_score(active, a.eval_games, a.eval_sims, a.baseline_level,
                          seed=a.eval_seed)
    report["current"] = current

    trained = []
    if any(s in steps for s in ("smoke", "tactics")) and npz.exists():
        r = arena_score(npz, a.eval_games, a.eval_sims, a.baseline_level,
                        seed=a.eval_seed)
        trained.append((npz, r))
    if "gpu" in steps and pt.exists() and HAS_TORCH:
        r = arena_score(pt, a.eval_games, a.eval_sims, a.baseline_level,
                        seed=a.eval_seed)
        trained.append((pt, r))
    for path, r in trained:
        report["candidates"].append({"path": str(path), **r})

    promoted_path = None
    reason = "kein Kandidat" if not trained else "no-promote gesetzt"
    if trained and not a.no_promote:
        best_path, best = max(trained, key=lambda x: x[1].get("score_lower95", 0.0))
        delta, delta_lower95, paired_games = paired_delta(best, current)
        report["gate"] = {
            "paired_games": paired_games,
            "mean_delta": round(delta, 3),
            "delta_lower95": round(delta_lower95, 3) if paired_games >= 2 else None,
            "candidate_score_lower95": best.get("score_lower95", 0.0),
            "min_games": 12,
            "min_score": a.min_score,
            "min_delta": a.min_delta,
        }
        ok = (paired_games >= 12
              and best.get("score_lower95", 0.0) >= a.min_score
              and delta_lower95 >= a.min_delta)
        if best_path.suffix == ".npz" and active_pt:
            ok, reason = False, "Torch-Checkpoint hat Vorrang; NumPy-Kandidat nicht aktiviert"
        elif not ok:
            reason = (f"Gate nicht bestanden: games={paired_games}/12, "
                      f"candidate lower95={best.get('score_lower95', 0.0)} "
                      f"(min {a.min_score}), paired Δ lower95="
                      f"{round(delta_lower95, 3) if paired_games >= 2 else 'n/a'} "
                      f"(min {a.min_delta})")
        if ok:
            target = ACTIVE_PT if best_path.suffix == ".pt" else ACTIVE_NPZ
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            if target.exists():
                backup = ARCHIVE / f"{target.stem}-{stamp}{target.suffix}"
                atomic_copy(target, backup)
                print(f"ARCHIV {backup}", flush=True)
            atomic_copy(best_path, target)
            promoted_path, reason = target, f"score={best['score']} ≥ Gate"
            print(f"PROMOTED {best_path} → {target}", flush=True)
        else:
            print(f"KEINE PROMOTION · {reason}", flush=True)
    else:
        print(f"KEINE PROMOTION · {reason}", flush=True)

    report["promoted"] = bool(promoted_path)
    report["active_after"] = str(promoted_path) if promoted_path else str(active or "")
    report["reason"] = reason
    report["duration_s"] = round(time.time() - t0, 2)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nreport={report_path}")
    print(f"dauer={report['duration_s']}s · aktiv={report['active_after'] or 'random'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
