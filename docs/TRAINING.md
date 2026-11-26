# Training Chess Garden from a terminal

**Nothing trains in the website.** The browser is for playing. `python ai/train_cli.py` is the only supported way to evaluate and promote a new active checkpoint; `train_basics.py`, `train_smoke.py`, `train_tactics.py` and `train_gpu.py` can create candidates but refuse to write directly to `checkpoints/model.npz` / `model_torch.pt`.

## Quick, safe experiment

```bash
python ai/train_cli.py --dry-run
python ai/train_cli.py --preset basics --basics-epochs 60 --max-seconds 120 --no-promote
```

`--dry-run` prints commands and writes **nothing**. The second command trains on a small curated curriculum, checks it on disjoint held-out positions and, if time remains, runs a paired evaluation. It cannot replace the active checkpoint because of `--no-promote`; the JSON report still includes whether the completed-game gate *would* pass. Reports and `.npz`/`.pt` candidates live in ignored `checkpoints/candidates/`.

## Presets

| Preset | Work |
|---|---|
| `basics` | Supervise curated moves plus ~220 legal synthetic capture/promotion/en-passant setups (including color/file augmentation); balance patterns during training and print eight-position held-out accuracy |
| `smoke` | Short CPU self-play sanity check |
| `tactics` | Distill tactical positions from the search engine; prints held-out mates separately from memorized training examples |
| `cpu` | `basics` → `smoke` → `tactics` |
| `gpu` | Explicit PyTorch self-play; CPU is possible but much slower |
| `auto` | CPU steps, then GPU only if CUDA is available |
| `eval` | Score the existing active checkpoint only; no training or promotion |

Use `--max-seconds N` to bound steps and Arena play (a single already-started move may finish after the deadline). `--strict` returns immediately on a failed subprocess; non-strict runs can continue, but **no failed run promotes a candidate**. `--seed` and `--eval-seed` control reproducibility. `--resume` must exist and match the checkpoint type trained by the preset. `--out` cannot point at an active checkpoint; stand-alone trainers also reject wrong formats and symlink aliases. On a 2 GB machine stick to `basics`/`smoke` or use the play-only `CHESS_LOW_RAM=1` server mode.

## Promotion is intentionally hard

When promotion is permitted, the CLI:

1. Evaluates active and candidate models against the same level-2 search opponent, same opening set and alternating colors.
2. Counts an illegal/absent move as a **loss**, never a draw. A game stopped by a ply or wall-time cap is **unfinished** and is excluded from both scoring and matched pairs.
3. Scores the **held-out** lessons; a training-set mate check is not a strength metric.
4. Requires >=12 completed matched games, candidate score lower 95% bound >= `--min-score` (default 0.55), paired gain lower 95% bound >= `--min-delta` (default 0.05), and fundamentals held-out accuracy >= `--min-basics-accuracy` (default 0.5). A NumPy candidate cannot displace an already approved Torch model.
5. Copies the old active checkpoint into `checkpoints/archive/`, atomically replaces it, then writes `model.approved.json` or `model_torch.approved.json` with its SHA-256 and gate report. The server checks the hash on startup; a partial/stale receipt cannot activate the model. **Restart the server** after a promotion.

With only 12–32 games, conservative one-sided 95% Hoeffding bounds on completed game scores and paired gains are a regression check, not proof of a chess rating. For credible strength gains, use far more finished paired games, separate tactical suites, stronger opponents and repeated seeds. Set `--no-promote` while experimenting.

**Observed sandbox run (2026-11-26):** `--preset basics --basics-epochs 60 --max-seconds 120 --eval-games 12 --eval-sims 8 --strict --no-promote` completed; the NumPy candidate scored **1/8 held-out** (unchanged) and **lost all 12 completed Arena games** against the level-2 search engine. The original checkpoint lost 11 games with one unfinished. The candidate was **not promoted**. This result is deliberately reported rather than described as a strong bot: the search engine is the reliable default until a candidate actually passes. A tiny smoke self-play run (14 positions) and tactics run (13 positions) also produced loadable *candidate* files, not promotion evidence.

## GPU (optional, not verified in this workspace)

On a compatible NVIDIA machine install a CUDA-enabled PyTorch build for the installed driver and then `python -m pip install -r requirements-gpu.txt`. Try:

```bash
bash ubuntu/train.sh --preset gpu --device cuda --games 200 --gpu-sims 60 \
  --eval-games 64 --max-seconds 14400
```

Torch checkpoint files include architecture dimensions (`channels`, `blocks`, `planes`) for loading custom-size ResNets. Old raw `state_dict` files are also readable. GPU self-play is currently sequential MCTS inference, **not batched**; hours of GPU runtime alone will not guarantee a strong model. A better replay scheme and stronger policy/value architecture are longer-term improvements.

## Reproducible quality checks

```bash
python -m unittest discover -s tests -v
npm run test:unit
```

`ai/lessons.py` splits teaching examples from held-out examples. A correct curriculum addition must be legal, use a distinct held-out position (not a color-flipped copy of the same mate), and pass `verify_lessons()`. Record results from multiple openings/seeds before promoting. The original `checkpoints/model.npz` is retained as an **unapproved comparison checkpoint**; live games use the search engine until a genuinely gated candidate is installed.
