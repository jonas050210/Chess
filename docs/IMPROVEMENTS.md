# Improvements · v6.2

## Jetzt umgesetzt

1. **Style-Reset:** Storybook-/Duolingo-inspiriertes Light-Theme als Default (`duo`); alte 5 Themes bleiben wählbar.
2. **Pieces nochmals neu:** 6 eigene Sticker-Silhouetten (Kreuz/Krone/Zinnen/Mütze/Pferd/Bauer), Gesichter, Marken, dicke Night-Ink-Outlines, frische Shades; 6 Themes × 2 Varianten × 12 = **144 PNGs in einer `assets/pieces.zip`**, direkt via `tk.PhotoImage(data=...)` geladen.
3. **GUI:** weiße Papier-Flächen, 2px Borders, grüne CTA mit 4px Lip, Blue-Hover, Tooltips, Pawn-Mascot in allen 3 Fenstern.
4. **Echt runde Tk-Widgets:** Cards, Checkboxen, OptionMenus, Spinboxen, Textfelder und Buttons nutzen Arc-basierte `RoundedFrame`/`round_rect` statt pixeliger Polygone. Tooltips binden mit `add="+"` und blockieren Hover/Klick nicht mehr.
5. **Fenster bewegbar:** `⋮⋮ ZIEHEN`-Header mit Drag-Bindings auf allen 3 Fenstern; Geometrie wird auf kleine Bildschirme geklemmt statt außerhalb zu liegen.
6. **Brett-Kontrast:** helle Felder `#ffffff`, dunkle `#a5ed6e` (Fresh Leaf) + 1px Grid, statt „komplett grün“.
7. **2-GB-RAM-Modus:** `windows\lowram.bat`, `ubuntu/lowram.sh`, `py main.py --low` → MCTS 4–24 Sims, Analyse-Thread aus, `OMP_NUM_THREADS=1`, Poll 1200 ms, kein Browser nötig.
8. **Drag & Animation:** Figur wird beim Ziehen aus dem Feld gehoben (Ghost in Tk + Browser); Züge gleiten in ~200 ms, Rochade animiert König **und** Turm, Promotion animiert den Bauern. Abschaltbar per Animation-Toggle / Low-RAM.
9. **Match-Mechanics:** Remis-Angebot mit Bot-Entscheidung, Abbruch vor Zug 2, Zugzeiten, Timeout, Inkrement, Premove, Unterverwandlung, 50-Züge/3-fach, Aufgabe, Remis-Einigung, Undo, Hint, Flip.
10. **Sync:** Theme/Textur/Pfeile/Premove/Koordinaten/Animation/Auto-Dame/Zeit/Level über `/api/settings` in Browser-UI und allen 3 Tk-Fenstern.
11. **Shortcuts:** `N` neu, `U` zurück, `H` Tipp, `F` drehen, `O` Remis anbieten, `A` Abbruch, `C` Markierungen löschen, `Esc` Premove abbrechen.
12. **Training v6 (nur Terminal):** `ai/train_cli.py`, Kandidaten statt destruktiver Checkpoints, Arena-Gate, Archiv/Backup, JSON-Report, Zeitbudget, Seeds, Early-Stopping, Matt-Check, CUDA-Erkennung. Details + Milestones: `docs/TRAINING.md`.
13. **Ordner-Struktur:** `web/` nur `index.html`; Docs in `docs/`, Vorschau in `assets/preview/`, Dev-Tools in `tools/`, Starter in `windows/` + `ubuntu/`. Gelöscht: `uploads/`, `image-search/`, alle losen Piece-/Preview-PNGs bis auf `all-preview.png`, `assets/pieces_svg/`, Demo-Kandidat/Log/Report, doppelte Root-Starter, Caches/Pycache.
14. **Preview:** genau **ein** persistentes PNG `assets/preview/all-preview.png`; Xvfb-Screenshot und alle Zwischen-SVGs/PNGs entstehen temporär und werden gelöscht.

## Als Nächstes würde ich machen

1. **Code vor Training:** Batch-Inference im MCTS, ResNet mit Legal-Policy-Head, bessere Eval (Mobilität/Königssicherheit/Bauern), Replay/League — das bringt aktuell mehr als längeres Trainieren.
2. Mehr Mascot-Gesichter / Reaktionen für Schach, Matt, Remis, Sieg — weiterhin eigene Vektoren.
3. XP/Streak/Rewards-Gamification: Genauigkeit, Bester Zug, Blunder-Tags, tägliche Challenge.
4. PGN-Export, Stellungs-URL, Eröffnungsname, Zugklassifizierung und Move-Review.
5. Puzzle-/Taktik-Modus mit gleichem Storybook-Board.
6. Arena-Dashboard direkt im Stats-Fenster (Win-Rate pro Checkpoint).
7. PyInstaller-Build für echte `Chess.exe` + Installer, zusätzlich zu `py main.py`.
8. Langer GPU-Lauf auf dem Heim-PC mit automatischem Eval-Gate, Checkpoint-Versionierung und Rollback.
