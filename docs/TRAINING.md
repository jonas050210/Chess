# Training v6 · nur Terminal

> Kein Trainings-Button in Browser oder Tk. Alles läuft über `ai/train_cli.py` bzw. `ubuntu/train.sh` / `windows/train.bat`.

## Was verbessert wurde

| Vorher | Jetzt |
|---|---|
| `train.sh` überschreibt `model.npz` direkt | Kandidaten unter `checkpoints/candidates/`, aktives Modell bleibt geschützt |
| Kein Gate | Arena vs. Baseline + `--min-score` / `--min-delta` vor Promotion |
| Fehler/Abbruch mittendrin ⇒ halber Checkpoint | JSON-Report, Archiv-Kopie, atomare `copy2`-Promotion |
| Feste lange Läufe | `--max-seconds`, `--dry-run`, Presets, `--no-promote` |
| Seeds nur pro Skript | ein `--seed` wird konsistent an Smoke/Taktik/GPU weitergegeben |
| Kein Early-Stopping | `--target-loss`, `--patience`, `--mate-check` in `train_tactics.py` |
| Leerer Replay-Buffer konnte crashen | `ReplayBuffer.sample()` liefert leere Arrays |
| GPU-Selfplay lief auch ohne CUDA los | `auto` erkennt Torch/CUDA und überspringt/schaltet auf CPU |

## Presets

| Preset | Ablauf |
|---|---|
| `auto` (Default) | Smoke → Taktik → GPU-Selfplay falls Torch → Arena → Gate |
| `cpu` | Smoke → Taktik → Arena → Gate |
| `gpu` | GPU-Selfplay → Arena → Gate (ohne Torch: nur Arena) |
| `smoke` | CPU-Smoke → Arena → Gate |
| `tactics` | Taktik-Distillation → Arena → Gate |
| `eval` | nur Arena gegen aktiven Checkpoint, kein Training |

## Befehle

```bash
# 1) Immer zuerst: Plan ohne Dateiänderungen
python3 ai/train_cli.py --dry-run

# 2) Kurzer CPU-Lauf mit Zeitbudget, keine Promotion
python3 ai/train_cli.py --preset cpu --max-seconds 120 --no-promote

# 3) Ernsthafter Ubuntu-Lauf mit CUDA
bash ubuntu/train.sh --preset auto --games 200 --gpu-sims 60 \
  --tactics-epochs 180 --eval-games 16 --min-score 0.60 --min-delta 0.05

# 4) Nur Stärke prüfen
python3 ai/train_cli.py --preset eval --eval-games 12 --eval-sims 30 --baseline-level 2

# 5) Windows-Terminal (CPU)
windows\train.bat --preset cpu --max-seconds 300 --no-promote
```

Wichtige Flags: `--device auto|cpu|cuda`, `--seed`, `--max-seconds`, `--resume`, `--out`, `--report`, `--min-score`, `--min-delta`, `--target-loss`, `--patience`, `--mate-check` (immer aktiv im CLI), `--no-promote`, `--strict`.

## Dateien

```text
checkpoints/
  model.npz              aktives NumPy-Modell (nur Promotion schreibt hier)
  model_torch.pt         aktives Torch-Modell, hat Vorrang (falls vorhanden)
  candidates/<run>.npz   NumPy-Kandidat
  candidates/<run>.pt    Torch-Kandidat
  candidates/<run>.json  Report: Commands, RCs, Arena-Scores, Promotion
  archive/<name>-<ts>    Backup vor Promotion
```

## Ehrliche Einordnung

Ja, ich kann hier im Terminal trainieren: CPU-Smoke + Taktik-Distillation laufen ohne GPU. In dieser Sandbox fehlen PyTorch/CUDA; GPU-Selfplay wird automatisch übersprungen. Ein kurzer Lauf erzeugt einen gültigen Kandidaten, **beweist aber keine Spielstärke**. Stärke braucht lange Selfplay-Läufe auf Ubuntu/GPU, ausreichend Arena-Spiele und ein positives Gate. Der Server bleibt währenddessen unangetastet und lädt erst nach bestandener Promotion das neue Modell.

**Längerer CPU-Lauf hier (33.2 s, `--no-promote`):** 124 Selfplay-Positionen, 197 Taktik-Samples, 60 Epochen, `loss 2.0818`, `mate_hit=4/4`. Arena bei 4 Spielen: `model.npz 0.125` vs. `demo.npz 0.0` → **Kandidat war schlechter**, korrekt keine Promotion. Das ist genau der Sinn des Gates: Taktik-MattTreffer allein sind noch keine Spielstärke. Kandidat, Log und Report wurden beim Cleanup gelöscht; die Zahlen stehen hier.

## Bringt Training etwas — oder ist Code besser?

**Kurzantwort: aktuell ist Code besser.** Regeln, `BaselineBot`, Taktik-Bonus, MCTS-Cache/Root-Reuse, Legal-Mask, Eval und UI liefern sofort messbare Züge. Training hat bei uns `mate_hit=4/4` erzeugt, aber die Arena trotzdem verloren. Ein kleines NumPy-MLP (1344 → 128 → 4672) + 40 MCTS-Sims lernt aus zu wenigen Selfplay-Partien kein Positionsverständnis.

Training wird erst sinnvoll, wenn **vorher** die Code-Basis besser ist:

1. Batch-Inference im MCTS (statt 1 Forward pro Sim) → 3–10× mehr Sims/s.
2. ResNet mit Legal-Policy-Head + Value-Target aus Spielausgang statt reinem Teacher-CP.
3. Bessere Bewertung: Mobilität, Königssicherheit, Bauernstruktur, Endspiel-Tabellen.
4. Replay mit Priorität/League/Selfplay-Gegnern statt nur Zufallsstellungen.
5. Arena mit genug Spielen + Konfidenz, nicht 2–4 Partien.

Auf dem **2-GB-i3-Laptop**: Training praktisch nur Smoke/Demo, kein Stärkegewinn. Auf dem **i7-12700F + RTX 4060 Ti 8 GB**: nach den Code-Fixes ja, dort bringt langes Selfplay etwas.

## Milestones · realistische Zeitabschätzung

Basis ist der gemessene Lauf oben: 3 Selfplay-Games/16 Sims = 3,0 s, 197 Taktik-Samples/60 Epochen = 17,8 s, Arena ≈ 1,5 s pro Partie bei 12 Sims. Werte sind **Schätzungen**, keine Garantie; 2 GB RAM bremst zusätzlich durch Swapping.

| # | Meilenstein | i3-1210U · 2 GB RAM (Windows-Laptop) | i7-12700F · 32 GB · RTX 4060 Ti 8 GB | Befehl |
|---|---|---:|---:|---|
| M0 | UI/Regeln/API laufen | 0 s (fertig) | 0 s (fertig) | `windows\lowram.bat` |
| M1 | Smoke-Checkpoint + `mate_hit=4/4` | 1–3 min | 0,5–2 min | `--preset cpu --max-seconds 180` |
| M2 | Taktik stabil: `loss<2.0`, 120 Epochen, 3 Seeds | 5–15 min | 3–8 min (GPU hilft kaum, NumPy) | `--preset tactics --tactics-epochs 120` |
| M3 | 40–100 Selfplay-Games, erste Arena > Baseline Lvl 1 (≥0,55 / 16 Spiele) | 30–90 min, nicht empfohlen | 15–45 min | `--preset auto --games 100 --eval-games 16` |
| M4 | Arena > Baseline Lvl 2/3 (≥0,60 / 32 Spiele) | viele Stunden bis Tage | 2–6 h | `--games 400 --gpu-sims 60 --eval-games 32` |
| M5 | „spürbar starke KI“ (konsistent gegen stärkere Gegner) | nicht realistisch | Tage + Code-Umbau | Batched MCTS, ResNet, League, Millionen Positionen |

**Wichtig:** M3–M5 sind mit dem aktuellen Code **nicht garantiert**. Unser 33-s-Lauf hat M1 erreicht, M2 teilweise, M3 **nicht** (Arena 0,0). Ohne die Code-Fixes oben kann auch ein 6-Stunden-Lauf auf der 4060 Ti nur ein besser angepasstes, aber immer noch schwaches MLP erzeugen. Meilensteine heißen hier: Gate bestanden — nicht „Engine-Stärke bewiesen“.
