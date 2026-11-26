# Ubuntu trainieren -> Windows spielen

Ja, das geht. Der Server braucht **keine GPU** zum Spielen; die GPU wird nur beim Trainieren in Ubuntu genutzt.

## 1. Ubuntu (Training, GPU)

```bash
cd chess-ai
pip3 install torch --index-url https://download.pytorch.org/whl/cu121   # passend zum Treiber
pip3 install -r requirements-gpu.txt
bash ubuntu/train.sh --preset auto --games 200 --eval-games 16 --max-seconds 3600
# Kandidaten + Gate; nur bei bestandenem Gate wird model_torch.pt / model.npz ersetzt
# CPU-Fallback: python3 ai/train_cli.py --preset cpu --max-seconds 600
```

## 2. Checkpoint nach Windows kopieren

Nur dieser Ordner muss rüber:

```
checkpoints/
```

Beispiel mit PowerShell auf Windows (Ubuntu-IP einsetzen):

```powershell
scp -r user@UBUNTU-IP:~/chess-ai/checkpoints C:\chess-ai\checkpoints
```

Oder USB-Stick / gemeinsamer Ordner / WSL-Mount.

## 3. Windows (Spielen)

```bat
windows\setup.bat
py main.py              :: 3 native Fenster
:: bei 2 GB RAM stattdessen:
windows\lowram.bat
:: nur Browser/Server:
windows\start.bat
```

Dann `http://localhost:8000` im Browser öffnen (nur bei `start.bat`). Details: `docs/RUN_ON_LAPTOP.md`.

- `model_torch.pt` wird nur genutzt, wenn Windows ebenfalls PyTorch + CUDA hat.
- Sonst nimmt der Server automatisch `model.npz` (CPU, NumPy) oder den Negamax-Baseline-Bot.
- Ohne jeden Checkpoint ist das Spiel trotzdem sofort spielbar.

## 4. Oder alles in Ubuntu

Einfach dort `python3 server.py` starten und `http://localhost:8000` öffnen. Training und Spielen am selben Rechner ist völlig ok.

## Kurzantwort

**Training Ubuntu/GPU + Spielen Windows = ja.**
**Alles in Ubuntu = auch ja, sogar einfacher.**
Der Code ist plattformneutral: Python + Browser, keine Windows-only-Abhängigkeiten.

## 5. Drei native Fenster statt Browser

Nach dem Kopieren genügt im Projektordner:

```bat
py main.py
```

Ubuntu:

```bash
python3 main.py
```

`main.py` startet den lokalen Server bei Bedarf selbst und öffnet drei kleine Tk-Fenster (Spiel, Bot/Rewards/Stats, Match/Settings). Voraussetzung: `tcl/tk` unter Windows (Python-Installer-Option) bzw. `python3-tk` unter Ubuntu. Checkpoint `checkpoints/model.npz` bleibt unverändert portabel.
