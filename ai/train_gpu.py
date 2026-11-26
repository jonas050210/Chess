"""Ubuntu/GPU-Trainer: Self-Play + PyTorch-ResNet + AMP + Eval + Checkpointing."""
from __future__ import annotations

import os
import sys
import argparse
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np

from ai.env import PLANES
from ai.evaluate import evaluate_vs_baseline
from ai.model import HAS_TORCH, TorchPolicyValueWrapper
from ai.selfplay import ReplayBuffer, play_selfplay_game


def main():
    ap = argparse.ArgumentParser(description="Rules-only Chess-AI auf Ubuntu/GPU trainieren")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--sims", type=int, default=25)
    ap.add_argument("--max-plies", type=int, default=80)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--train-every", type=int, default=2)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--value-weight", type=float, default=1.0)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--lr-step", type=int, default=10)
    ap.add_argument("--lr-gamma", type=float, default=0.85)
    ap.add_argument("--buffer", type=int, default=20000)
    ap.add_argument("--channels", type=int, default=64)
    ap.add_argument("--blocks", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--device", default=None)
    ap.add_argument("--resume", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "checkpoints", "model_torch.pt"))
    ap.add_argument("--save-every", type=int, default=10)
    ap.add_argument("--eval-every", type=int, default=10)
    ap.add_argument("--eval-games", type=int, default=4)
    ap.add_argument("--max-seconds", type=int, default=0, help="0 = unbegrenzt")
    args = ap.parse_args()

    if not HAS_TORCH:
        print("PyTorch fehlt. Auf Ubuntu zuerst:")
        print("  pip3 install torch --index-url https://download.pytorch.org/whl/cu121")
        print("  pip3 install -r requirements-gpu.txt")
        return

    import torch
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.startswith("cuda")
    dev_type = "cuda" if use_amp else "cpu"
    print(f"device={device} amp={use_amp} torch={torch.__version__} planes={PLANES}")
    if use_amp:
        p = torch.cuda.get_device_properties(device)
        print(f"gpu={p.name} vram={p.total_memory / 1024**3:.1f} GiB")

    net = TorchPolicyValueWrapper(
        channels=args.channels, blocks=args.blocks, device=device,
        checkpoint=args.resume if args.resume and os.path.exists(args.resume) else None,
    )
    opt = torch.optim.Adam(net.net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=args.lr_step, gamma=args.lr_gamma)
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
    buf = ReplayBuffer(capacity=args.buffer)
    rng = np.random.default_rng(args.seed)

    def train_steps(n: int) -> float:
        net.net.train()
        losses = []
        for _ in range(n):
            x, m, pi, z = buf.sample(args.batch)
            if len(x) == 0:
                break
            xt = torch.from_numpy(x).reshape(-1, PLANES, 8, 8).to(device)
            mt = torch.from_numpy(m).to(device)
            pit = torch.from_numpy(pi).to(device)
            zt = torch.from_numpy(z).to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev_type, enabled=use_amp):
                logits, v = net.net(xt, mt)
                logp = torch.log_softmax(logits, dim=1)
                policy_loss = -(pit * logp).sum(dim=1).mean()
                value_loss = torch.mean((v - zt) ** 2)
                loss = policy_loss + args.value_weight * value_loss
            scaler.scale(loss).backward()
            if use_amp:
                scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.net.parameters(), args.grad_clip)
            scaler.step(opt)
            scaler.update()
            losses.append(float(loss.item()))
        sched.step()
        net.net.eval()
        return sum(losses) / len(losses) if losses else 0.0

    t0 = time.time()
    for g in range(args.games):
        if args.max_seconds and time.time() - t0 > args.max_seconds:
            print("max-seconds erreicht, breche ab")
            break
        recs = play_selfplay_game(net, simulations=args.sims,
                                  max_plies=args.max_plies, rng=rng, noise_eps=0.25)
        buf.add_game(recs)
        print(f"[game {g+1:>3}/{args.games}] pos={len(recs):>3} buffer={len(buf.data):>5} "
              f"lr={sched.get_last_lr()[0]:.2e}", flush=True)

        if (g + 1) % max(1, args.train_every) == 0:
            print(f"          train loss={train_steps(args.epochs):.4f}", flush=True)
        if args.eval_every and (g + 1) % args.eval_every == 0:
            r = evaluate_vs_baseline(net, games=args.eval_games, sims=args.sims, level=2)
            print(f"          eval +{r['win']} ={r['draw']} -{r['loss']} score={r['score']}", flush=True)
        if args.save_every and (g + 1) % args.save_every == 0:
            step_path = args.out.replace(".pt", f".step{g+1}.pt")
            net.save(step_path)
            print(f"          saved {step_path}", flush=True)

    net.save(args.out)
    print(f"saved  {args.out}")
    print(f"time   {time.time() - t0:.1f}s | buffer={len(buf.data)}")


if __name__ == "__main__":
    main()
