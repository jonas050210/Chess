# Engineering notes · web-only Chess Garden

## Delivered in this branch

- Replaced the three Tk windows, ZIP of low-resolution PNG pieces, and schematic preview with a responsive web-first game, original scalable SVG chess art, real browser screenshot, and self-hosted assets.
- Rules stay in `python-chess`. Claimable draws no longer auto-end games or override an expired clock; bot-game claims require the human's turn; draw agreements require an actual opponent's offer; undo restores clocks, increments and move statistics; captured-piece displays follow actual captures rather than miscounting promoted pawns; errors validate JSON types and return 400 instead of 500.
- Per-browser in-memory games, same-origin checks, sessionStorage fallback for embedded previews; async bot/analysis outside the game lock, with stale search results discarded after undo/new/timeout.
- Reliable alpha-beta playing search by default; check-aware quiescence, mate scoring, king safety and pawn structure. Model activation requires a SHA-256 receipt from the gated terminal trainer.
- Disjoint basic lessons with mechanically verified synthetic positions, incomplete-game-aware Arena and self-play labels, protected candidate paths, strict training error propagation, architecture-aware Torch checkpoints. The measured candidate still failed the gate (see [Training](TRAINING.md)); this is intentionally not advertised as a strength gain.
- Python rules/API/training tests, JS board/art tests, real Chromium tests for click/drag/touch moves, undo, draw, premove, promotion, PGN export, board annotations, orientation and mobile layouts in CI.

## Honest remaining limits and valuable future work

1. **Measure real strength**, not just a few mate puzzles. Build a larger independent annotated tactical/endgame test set, run hundreds of completed paired games against several opponent strengths and publish the results. The small training curriculum is illustrative, not a rating.
2. **Improve model search efficiency.** MCTS currently calls the policy/value net per leaf; batched inference, tree reuse across self-play and an upgraded policy head/replay scheme should precede any long GPU run. PyTorch/CUDA training still needs end-to-end testing on actual hardware.
3. **Persist games** if needed beyond a local session. Browsers are isolated but in-memory positions are lost on server restart; saving PGN manually works now. A database can be added without putting a login or training UI in the game.
4. **Add deeper learning modes** after core strength is measured: verified tactical puzzles, post-game move review and feedback. A small local search should not label every move a "blunder" as if it were a master engine.
5. **Harden deployment** before any public hosting. Host binding defaults to localhost and the reverse-proxy preview is not authenticated. A public service would need authentication, rate limits, persistence and resource quotas; cookies/opaque IDs only isolate games.
6. **Polish accessibility** with screen-reader play testing, richer announcements for promotion and clock events, and touch-friendly annotation gestures. The existing board supports arrow-key navigation and reduced-motion preferences.
