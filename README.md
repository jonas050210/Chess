# Chess Bot v6.2

A **fully local, self-contained chess bot** with a browser UI, three native Tkinter windows, custom sticker pieces, drag & drop, move animation, and a terminal-only training pipeline.

No cloud services. No external images, fonts, or CDN assets. No Chess.com automation. No Stockfish/LC0 binaries. Everything needed to run lives in this folder.

> This `README.md` is the **single canonical English project description for GitHub**. It replaces the earlier idea of a separate `project.md`. The filename is `README.md` (GitHub standard), not `read.me.md`. Older notes under `docs/` are archived working notes and are not required to run or understand the project.

---

## 1. TL;DR for an AI agent / reviewer

```yaml
project: Chess Bot v6.2
purpose: local chess game + bot + terminal-only training pipeline
language: Python 3.10+
stack: Flask, python-chess, NumPy, Tkinter, optional PyTorch/CUDA
entry_points:
  browser_api: python3 server.py
  desktop_ui: python3 main.py
  training: python3 ai/train_cli.py
runtime_binaries:
  - checkpoints/model.npz          # active NumPy policy/value model
  - assets/pieces.zip              # 144 piece images loaded directly by Tk
  - assets/preview/all-preview.png # one preview image
constraints:
  - no runtime network calls
  - no foreign logos/assets/fonts
  - no training buttons in the GUI
  - active checkpoint is never overwritten without a passing Arena gate
  - training is terminal work only
honesty:
  tested: rules, API, UI, drag, animation, settings sync, low-RAM mode, training pipeline
  not_proven: strong playing strength; short CPU runs are smoke tests only
repo_size: about 4 MB, about 44 files
version: v6.2
```

---

## 2. What it does

- Play chess against a local bot. You always start as White; the bot never moves before your first move.
- Choose between a **self-contained browser UI** at `http://127.0.0.1:8000` and **three native Tk windows** started by `main.py`.
- Pieces are **custom Storybook-style stickers**: King with cross, Queen with crown, Rook with battlements, Bishop with mitre, Knight with horse head, Pawn with round head. All have thick outlines, small faces, accent marks, and six color themes × `textured` / `flat`.
- **Drag & drop**: the piece is lifted from its square and a ghost follows the cursor in both Tk and the browser.
- **Move animation**: moves glide in about 200 ms. Castling animates King **and** Rook; promotion animates the pawn before the new piece appears. Can be disabled with the Animation toggle; disabled automatically in low-RAM mode.
- **Rounded Tk widgets**: cards, checkboxes, option menus, spinboxes, text areas, and buttons use real arc-based corners instead of pixelated polygons.
- **Movable windows**: every Tk window has a `⋮⋮ DRAG` header; geometry is clamped to small screens.
- **Board contrast**: light `#ffffff`, dark `#a5ed6e`, plus a 1 px grid — not a solid green board.
- **Settings sync** across browser + all three Tk windows via `/api/settings`: theme, texture, arrows, premove, coordinates, animation, auto-queen, time, level, highlight.
- **Mechanics**: legal moves, check/mate/stalemate, 50-move and threefold rules, insufficient material, castling, en passant, promotion/underpromotion, undo, hint, flip, resignation, draw offer/claim/agreement, abort before move 2, clocks, increment, premove, right-click marks/arrows, last-move arrow, hover/premove highlights, low-time clocks, material difference, live eval bar, captured pieces, FEN/PGN.
- **Shortcuts**: `N` new game, `U` undo, `H` hint, `F` flip, `O` offer draw, `A` abort, `C` clear marks, `Esc` cancel premove.
- **Stats & analysis**: engine/device/checkpoint, MCTS sims/cache, search depth/nodes, best move, PV, eval, tactics tags, reaction times, reward, W/D/L, clocks, rule status.
- **Training v6**: terminal-only orchestrator with candidate checkpoints, Arena gate, archive/backup, JSON report, time budget, seeds, early stopping, mate check, CUDA detection. No GUI training controls.

---

## 3. Quick start

### Windows

PowerShell clone, install, play, test, and training commands: [`docs/POWERSHELL_WINDOWS.md`](docs/POWERSHELL_WINDOWS.md).

1. Install Python 3.10+ from python.org. Enable **"tcl/tk and IDLE"** and the **py launcher**.
2. In the `chess-ai` folder:

```bat
py -m pip install -r requirements.txt
py main.py
```

Other starters:

```bat
windows\launch3.bat      :: 3 native windows, normal mode
windows\lowram.bat       :: 3 native windows, 2 GB RAM mode
windows\start.bat        :: browser/server only
windows\setup.bat        :: one-time dependency install
```

### Ubuntu / Linux

```bash
sudo apt update
sudo apt install python3-tk python3-pip
python3 -m pip install -r requirements.txt
python3 main.py
# or:
bash ubuntu/lowram.sh
python3 server.py        # browser/server only
```

Browser: <http://127.0.0.1:8000>

If port 8000 is busy, set **both** variables to the same value:

```bash
PORT=8001 CHESS_PORT=8001 python3 server.py
PORT=8001 CHESS_PORT=8001 python3 main.py
```

Windows equivalent: `set PORT=8001` and `set CHESS_PORT=8001` before starting.

The API binds to `127.0.0.1` by default. It has no authentication; keep that default unless you intentionally need LAN access. To expose it on a trusted, firewalled network only, set `CHESS_HOST=0.0.0.0` before starting the server.

---

## 4. 2 GB RAM laptop mode

Use `windows\lowram.bat`, `bash ubuntu/lowram.sh`, or `py main.py --low`.

It reduces MCTS to 4–24 simulations, disables the continuous analysis thread, sets `OMP_NUM_THREADS=1`, polls every 1200 ms instead of 600 ms, and skips move animation. Do **not** also keep Chrome open on a 2 GB machine; the three Tk windows are enough.

Verified: `low_ram=True`, `sims=12` at level 3, `analysis.thinking=False`, `analysis.result=None`.

---

## 5. Repository layout

| Path | Contents |
|---|---|
| `README.md` | This canonical English project description |
| `main.py` | Three Tk windows, drag/animation, rounded widgets, settings UI |
| `server.py` | Flask API, async bot, analysis thread, clocks, draws, stats |
| `web/index.html` | Self-contained browser UI; embedded SVG piece generator; no external refs |
| `ai/` | Environment, 21-plane tensor, 4672-action space, NumPy MLP, MCTS, baseline negamax, tactics, analysis, stats, training CLI |
| `assets/pieces.zip` | 144 PNGs: 6 themes × 2 variants × 12 pieces; loaded directly by Tk |
| `assets/preview/all-preview.png` | The only persistent preview image |
| `checkpoints/model.npz` | Active NumPy model, about 2.8 MB, already compressed |
| `docs/` | Archived German working notes: laptop guide, training, improvements, style research |
| `tools/` | Dev-only generators: `generate_assets.js`, `render_assets.py`, `capture_ui.py`, `make_preview.py` |
| `windows/`, `ubuntu/` | Starters, setup, low-RAM wrappers, training wrappers |
| `requirements.txt`, `requirements-gpu.txt` | CPU and optional CUDA dependencies |
| `.gitignore` | Ignores caches, temporary previews, candidate checkpoints, logs |

Only three binary files are required at runtime: `assets/pieces.zip`, `assets/preview/all-preview.png`, `checkpoints/model.npz`. There are **no loose piece PNGs** anymore.

---

## 6. How it works

- `server.py` owns one `python-chess` board, clocks, settings, stats, draw state, and an asynchronous bot worker.
- `AIBot` prefers a Torch checkpoint if present, then the NumPy MLP, then a deterministic negamax/quiescence/PST baseline. MCTS uses 8/20/40/80/150 simulations by level (4/8/12/16/24 in low-RAM mode).
- `AnalysisEngine` runs a continuous depth-2 → depth-3 search in the background (disabled in low-RAM mode).
- `web/index.html` generates piece SVGs in JavaScript and talks only to the local Flask API.
- `main.py` loads PNGs from `assets/pieces.zip` via `tk.PhotoImage(data=...)`, derives 32 px capture icons with `subsample(2,2)`, and renders everything on Tk canvases.
- `tools/make_preview.py` regenerates `assets/pieces.zip` and `assets/preview/all-preview.png` from temporary SVGs; all intermediate files are deleted afterwards.

Key API endpoints: `/api/state`, `/api/new`, `/api/move`, `/api/undo`, `/api/hint`, `/api/settings`, `/api/analysis`, `/api/stats`, `/api/offer_draw`, `/api/claim_draw`, `/api/agree_draw`, `/api/abort`, `/api/resign`.

---

## 7. Training — terminal only

```bash
python3 ai/train_cli.py --help
python3 ai/train_cli.py --dry-run
python3 ai/train_cli.py --preset cpu --max-seconds 300 --no-promote
bash ubuntu/train.sh --preset auto --max-seconds 1800 --eval-games 32
```

Windows:

```bat
windows\train.bat --preset cpu --max-seconds 300 --no-promote
```

With an NVIDIA GPU on Ubuntu:

```bash
pip3 install torch --index-url https://download.pytorch.org/whl/cu121
pip3 install -r requirements-gpu.txt
bash ubuntu/train.sh --preset auto --games 200 --gpu-sims 60 --eval-games 32 --max-seconds 3600
```

Every run writes **candidates** to `checkpoints/candidates/`, a JSON report, and archives the active model before a promotion. `model.npz` / `model_torch.pt` are never overwritten directly. Without `--no-promote`, a candidate replaces the active model only after a positive Arena gate.

### Honest milestone estimates

Measured baseline: 3 selfplay games / 16 sims = 3.0 s, 197 tactic samples / 60 epochs = 17.8 s, about 1.5 s per Arena game at 12 sims. Estimates are not guarantees; 2 GB RAM swaps heavily.

| Milestone | i3-1210U · 2 GB Windows laptop | i7-12700F · 32 GB · RTX 4060 Ti 8 GB |
|---|---:|---:|
| M0 UI/rules/API working | 0 s · done | 0 s · done |
| M1 smoke checkpoint + mate 4/4 | 1–3 min | 0.5–2 min |
| M2 stable tactics, 120 epochs | 5–15 min | 3–8 min |
| M3 first Arena win vs baseline level 1 | 30–90 min, not recommended | 15–45 min |
| M4 Arena win vs level 2/3 | hours–days | 2–6 h |
| M5 "noticeably strong" | not realistic | days + code rework |

**Current status:** a 33.2 s CPU run produced `loss 2.0818`, `mate_hit=4/4`, but lost the Arena `0.0` vs `0.125`. Correctly **no promotion**. Rules/UI/API/pipeline are reliable; playing strength is **not proven**. Code improvements (batched MCTS inference, ResNet with legal policy head, better evaluation, replay/league) currently matter more than longer training.

---

## 8. Hardware notes

| Machine | Use |
|---|---|
| Windows laptop, i3-1210U, 2 GB RAM | Play with `windows\lowram.bat`; training only as smoke test |
| Home PC, i7-12700F, 32 GB DDR4, RTX 4060 Ti 8 GB | Real GPU training after code improvements |
| This sandbox | CPU only, no PyTorch/CUDA, no GPU selfplay |

---

## 9. Upload to GitHub

Yes, the whole folder can be uploaded. **Arena does not offer a GitHub connector in this conversation**, so I cannot push directly from here. Use Git on your laptop or GitHub Desktop.

Create an empty repository on GitHub first (do **not** add a README there), then:

```bash
cd chess-ai
git init
git add .
git commit -m "Chess Bot v6.2"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

GitHub Desktop alternative: `File → Add local repository… → choose chess-ai → Publish repository`.

`.gitignore` already excludes `__pycache__/`, `*.pyc`, `.preview-tmp/`, `checkpoints/candidates/`, `checkpoints/archive/`, `*.log`, `.DS_Store`, `Thumbs.db`. A leftover dry-run report with absolute sandbox paths was removed during GitHub preparation. No credentials, tokens, or API keys are stored in the repository.

If you want a literal `project.md` in addition to this file, copy this README — but the final decision was **everything in `README.md`**.

---

## 10. Cleanup / size

Deleted: `uploads/`, `image-search/`, loose piece PNGs/SVGs, `assets/pieces_svg/`, duplicate 32 px icons, fallback preview PNG, demo candidate/log/report, duplicate root starters, caches and `__pycache__`.

Kept: one ZIP, one preview PNG, one model checkpoint, source, docs, dev tools, starters, requirements, `.gitignore`.

Current repository: about **4 MB**, about **44 files**, 0 external references in `web/index.html`, 0 loose piece PNGs.

---

## 11. Verification

Run the maintained regression suite (CPU/low-RAM mode; no GUI required):

```bash
CHESS_LOW_RAM=1 python3 -m unittest discover -s tests -v
python3 -m compileall -q ai server.py main.py tools tests
```

The suite covers clock start/flag fall, MCTS cache identity, paired Arena comparisons, and safe checkpoint replacement. GitHub Actions runs it on Python 3.10 and 3.12.

Previously performed manual checks:

- `python3 -m py_compile ai/*.py server.py main.py tools/*.py`
- `node --check tools/generate_assets.js` and extracted browser JS
- Xvfb UI test: titles, geometry, 12 images from ZIP, 32 px capture icons, drag `e2 → e4`, ghost visible, `animating=True hide=['e4'] → False`, `san=['e4']`, button click, header drag
- Low-RAM API test: `sims=12`, `analysis.thinking=False`
- API smoke: fresh game `playing / w / bot_thinking=False / san=[] / theme=duo / animation=True`
- `python3 ai/train_cli.py --dry-run`
- `python3 tools/make_preview.py` regenerates ZIP + preview from temporary sources

---

## 12. Known limitations / localization

- This README and `.gitignore` are in English and are the GitHub-facing documentation. In-app labels, comments, and the archived `docs/*.md` notes are still German. A full UI/comment translation is a separate, non-breaking pass — ask for it explicitly if you want every string converted.
- No `.exe` is built; `py main.py` is the cross-platform entry point.
- No opening book, no endgame tablebases, no Stockfish/LC0. The NumPy MLP is small; Arena gates protect against regressions but do not prove engine strength.
- GPU training was not end-to-end tested in this sandbox because PyTorch/CUDA are absent.

---

## 13. License

Add your own `LICENSE` file before publishing if you want a specific license. Until then, all rights are reserved by the repository owner.

---

**Version:** v6.2 · Storybook style, new sticker pieces from one ZIP, drag & animation, low-RAM mode, terminal-only training, English GitHub README.
