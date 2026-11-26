# Chess Garden

A **browser-only, local chess game** with friendly, Duolingo-inspired (not Duolingo-branded) design, original faceless Staunton-inspired SVG pieces, a rule-authoritative Python server, and **terminal-only** bot training. There is no Tkinter app, training button, CDN, external image/font, account, or cloud engine.

![Real browser screenshot of Chess Garden](docs/web-preview.png)

## Play

Python 3.10+ is required. **After one-time setup, `py main.py` (Windows) or `python3 main.py` (Linux) starts the local server and opens the default browser** at http://127.0.0.1:8000/. Keep the terminal open while playing; Ctrl+C stops the server. The launcher automatically uses this repository's `.venv` when it exists, even when you invoke it with the global Python.

**Windows PowerShell (new installation; Git for Windows and the Python launcher required):**

```powershell
git clone https://github.com/jonas050210/Chess.git
cd Chess
.\windows\setup.bat
py main.py
```

If the **`Chess` folder already exists**, `git clone` cannot clone into it. Save any local edits first; from that folder, update the existing checkout instead:

```powershell
cd Chess
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
.\windows\setup.bat
py main.py
```

If `git status --short` shows changes you want to keep, commit or otherwise save them **before** switching/pulling. `windows\start.bat` is an alternative to `py main.py` and also opens the browser. For low-RAM play in PowerShell: `$env:CHESS_LOW_RAM='1'; py main.py` (or `bash ubuntu/lowram.sh` on Linux). This disables continuous analysis; the default search bot's idle RAM savings are small.

**Linux (new installation, from the repository root):**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 main.py
```

For a different port: `PORT=8001 python3 main.py` (PowerShell: `$env:PORT=8001; py main.py`). For an unattended server without opening a browser, set `CHESS_NO_BROWSER=1`, or run `python server.py`. Flask's automatic `.env`/`.flaskenv` loading is deliberately disabled: a Windows PowerShell 5.1 UTF-16 `.env` otherwise makes Flask crash before it starts. Use process environment variables such as `$env:CHESS_LOW_RAM='1'` instead; you do not need to delete an old `.env` to play. The default bind address is **127.0.0.1**. `CHESS_HOST=0.0.0.0` is intended only for trusted networks or the Arena live preview: **this is not an authenticated public service**. Browser games live in memory and disappear on server restart; separate clients have separate games (a cookie plus a session-storage fallback for embedded previews).

### Controls

- Click a piece and a destination, drag a piece, or focus the board and use **arrow keys + Enter**. Legal moves and checks are highlighted. Promotion offers queen, rook, bishop, and knight unless auto-queen is enabled.
- The ⛶ **Fullscreen** button fills the screen with the board and its left time panel (Exit fullscreen/Esc to leave; F11 if your browser blocks the Fullscreen API). Above the central **total game time** are the bot's total thinking time and last move in seconds/milliseconds; below are yours. There is **no countdown, increment or timeout**; these are stopwatches, not limits.
- Start a new game as White or Black. **New game and each page reload reset all pieces to the standard starting position**, including the times and move history. Reloading discards an unfinished game; save its PGN first if needed. Undo (a full human/bot turn once the bot replies, or just your pending move while it thinks), hint, board flip and PGN download remain available.
- While the bot thinks, you can undo or start a new game, but cannot move your pieces until it is your turn: **no queued premoves**. Right-click a square to mark it or drag with the right button to draw an arrow. Escape clears marks/selection.
- **Shortcuts:** `N` new game, `U` undo, `H` hint, `F` flip, `O` offer draw, `A` abort early, `C` clear marks, `Esc` cancel. Preferences contain animation, coordinates, board colors and local two-player mode.
- Chess rules come from `python-chess`: legal moves, castling, en passant, underpromotion, check/mate/stalemate, automatic fivefold/75-move/insufficient-material draws, **claimable** threefold/50-move draws, agreement and resignation. An offer to a friend needs the other side to accept; the bot may accept or decline an offer.

### What the bot actually is

The default playing bot uses a **bounded alpha-beta search** with check-aware quiescence, mate scoring, move ordering, material, pawn-structure and king-safety evaluation. It always uses the **strongest built-in setting (level 5: depth up to 5, about 4 seconds of search per move)**; there is no difficulty selector or artificial move-choice jitter. This is *not* a grandmaster engine and it can still make mistakes. Hints use the same local engine. Live analysis only searches when you open its panel, so it does not constantly compete with the bot for CPU. The optional policy/value checkpoint is **not** used in live games simply because a `.npz` file exists: it needs a matching SHA-256 receipt for a successful gate **against level-5 search**. Older approvals against a weaker opponent are not enough. Restart the server after promotion. `CHESS_ENGINE=baseline` forces search for comparisons; `CHESS_ENGINE=model` is an explicit experimental override that can play worse.

## Improve the bot (terminal only)

```bash
python ai/train_cli.py --dry-run
python ai/train_cli.py --preset basics --basics-epochs 60 --max-seconds 120 --no-promote
python ai/train_cli.py --preset tactics --tactics-positions 60 --tactics-epochs 30 --max-seconds 300 --no-promote
python ai/train_cli.py --preset cpu --max-seconds 900 --eval-games 32
# Optional PyTorch/CUDA training on a suitable machine:
python -m pip install -r requirements-gpu.txt
bash ubuntu/train.sh --preset gpu --device cuda --games 200 --eval-games 32
```

Windows PowerShell: `.\windows\train.bat --preset tactics --tactics-positions 60 --tactics-epochs 30 --max-seconds 300 --no-promote` (or use `--preset basics`). **Each new CLI training run resumes the last successfully saved compatible candidate weights** from `checkpoints/candidates/latest.json` rather than restarting from the original model. Each stage writes a new checkpoint; a failed stage cannot overwrite its predecessor. `--dry-run` prints the chosen source without writing. If the recorded checkpoint is missing or changed, training stops with an error rather than silently resetting; `--resume PATH` explicitly chooses another compatible source. If no prior candidate exists, the first run starts from the existing active checkpoint if available. This continues **weights**, not PyTorch optimizer state or self-play replay history.

The **basics curriculum** (`ai/lessons.py`) teaches mate-in-one, hanging captures, development, king safety, promotion, en passant and opening moves, plus mechanically verified simple capture/promotion/en-passant examples. Its separate eight held-out positions report *move-prior accuracy*, **not playing strength**. `--preset tactics` works on generated capture and mate scenarios; `--preset cpu` runs basics → bounded self-play → tactics. Training runs **in the terminal, never the browser**. By default, training writes to ignored `checkpoints/candidates/`; a custom `--out` may choose another non-active candidate path. The active checkpoint is never the direct output of a trainer. Only a successful gate against level-5 search with at least **12 completed paired games**, a conservative 95% lower score/gain, and a held-out fundamentals check may atomically promote a candidate. An invalid move counts as a loss; an unfinished game does **not** count as a draw. If the gate fails, the live bot continues using the reliable search engine. A previous tiny experiment scored 1/8 on held-out basics and lost all 12 completed Arena games; it was **not promoted**. More training is not a guarantee of improvement. Details: [Training guide](docs/TRAINING.md).

## Tests and development

```bash
python -m unittest discover -s tests -v
python -m compileall -q ai server.py main.py tests
npm run test:unit                      # pure browser logic and SVG art; Node 22+
npm ci && npx playwright install chromium
npm run test:e2e                       # real browser, Python server required on PATH
```

CI runs Python tests on 3.10 and 3.12, a Windows PowerShell 5.1 launch check with a UTF-16 `.env`, Node unit tests, and Chromium browser tests covering click/drag/touch play, undo, draws, queued-move rejection, elapsed time/fullscreen, reload reset, promotions, annotations, PGN export, pieces and 360–1440px layouts. The Playwright config starts the server automatically; activate the Python environment before running it locally. For an iframe preview, start with `CHESS_HOST=0.0.0.0 python server.py`; the website calls the API through **relative URLs** only.

| Path | Purpose |
|---|---|
| `web/index.html`, `web/styles.css`, `web/app.js` | Browser UI and responsive interaction |
| `web/pieces.js`, `web/logic.js` | Original scalable art and independently tested board helpers |
| `server.py` | Per-browser sessions, elapsed-time stopwatches, legal moves, draws, async bot and analysis API |
| `ai/baseline.py`, `ai/bot.py` | Playing search and gated model selection |
| `ai/lessons.py`, `ai/train_basics.py`, `ai/train_cli.py`, `ai/checkpoint_lineage.py` | Terminal curriculum, resumable candidate lineage and guarded promotion |
| `ai/mcts.py`, `ai/model.py`, `ai/selfplay.py`, `ai/evaluate.py` | Optional policy/value model, self-play and paired Arena |
| `tests/`, `.github/workflows/tests.yml` | Python, JS and browser regression tests |
| `checkpoints/model.npz` | Existing model retained for comparisons; not approved by default |

### Limits

Chess Garden runs locally, not as a hosted multiplayer product: games are not saved on server restart, no user accounts exist, and opening books/tablebases are not included. GPU training has not been run end-to-end in this sandbox. The held-out lessons are deliberately small and the NumPy model can overfit even the expanded training set; stronger chess needs substantially more high-quality data and completed Arena evidence, not a claim based on training loss alone. See [improvements and next steps](docs/IMPROVEMENTS.md).

No `LICENSE` is present; permission to reuse this code or artwork is not implied without one from the owner.
