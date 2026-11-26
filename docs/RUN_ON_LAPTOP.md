# Auf dem Laptop runnen · Copy & Paste

Kopiere den **kompletten Ordner `chess-ai/`** auf den Laptop (ZIP/USB/Git). Alles bleibt lokal: keine Cloud, keine externen Bilder/Fonts, keine `.exe` nötig.

## Windows

1. Python 3.10+ installieren: <https://www.python.org/downloads/windows/>  
   **Wichtig:** Haken bei **„tcl/tk and IDLE“** setzen (sonst fehlen die 3 Tk-Fenster).
2. Im Ordner `chess-ai` ein Terminal öffnen:

```bat
py -m pip install -r requirements.txt
py main.py
```

Alternative Starts:

```bat
windows\start.bat        :: nur Browser/Server
windows\launch3.bat      :: 3 native Fenster (Normalmodus)
windows\lowram.bat       :: 3 Fenster im 2-GB-Modus
```

**Dein 2-GB-Laptop:** bitte `windows\lowram.bat` nehmen (oder `py main.py --low`). Das startet nur die 3 Tk-Fenster, schaltet den Dauer-Analyse-Thread aus, reduziert MCTS auf 4–24 Sims, setzt `OMP_NUM_THREADS=1` und pollt nur alle 1200 ms. Browser/Chrome zusätzlich offen lassen ist bei 2 GB RAM keine gute Idee. Fenster am `⋮⋮ ZIEHEN`-Header verschieben.

```bat
windows\lowram.bat
```

Browser-URL (nur bei `windows\start.bat`): <http://127.0.0.1:8000>

## Ubuntu / Linux

```bash
sudo apt update
sudo apt install python3-tk python3-pip
python3 -m pip install -r requirements.txt
python3 main.py          # 3 native Fenster
# oder:
bash ubuntu/lowram.sh    # 3 Fenster im 2-GB-Modus
python3 server.py        # nur Browser/Server
```

Browser-URL: <http://127.0.0.1:8000>

Falls Port 8000 belegt ist, **beide** Variablen gleich setzen:

```bash
PORT=8001 CHESS_PORT=8001 python3 server.py
PORT=8001 CHESS_PORT=8001 python3 main.py
```

Windows analog: `set PORT=8001` + `set CHESS_PORT=8001` vor dem Start.

## Training · nur Terminal

Keine Trainings-Buttons in der UI. Immer zuerst den Plan ansehen:

```bat
windows\train.bat --dry-run
windows\train.bat --preset cpu --max-seconds 600 --no-promote
```

```bash
bash ubuntu/train.sh --dry-run
bash ubuntu/train.sh --preset cpu --max-seconds 600 --no-promote
```

### Mit NVIDIA-GPU auf Ubuntu

```bash
pip3 install torch --index-url https://download.pytorch.org/whl/cu121
pip3 install -r requirements-gpu.txt
bash ubuntu/train.sh --preset auto --games 200 --gpu-sims 60 \
  --tactics-epochs 180 --eval-games 32 --max-seconds 3600
```

Ohne `--no-promote` darf der Kandidat erst nach bestandenem Arena-Gate `model.npz` / `model_torch.pt` ersetzen; vorher wird archiviert. Details: `docs/TRAINING.md`.

## Was ich hier schon gemacht habe

Ich habe in der Sandbox einen längeren **CPU-Lauf** ausgeführt (33 s): Kandidat erzeugt, Matt-Check `4/4`, aber Arena `0.0` gegen `0.125` → keine Promotion. Kandidat, Report und Log wurden beim Cleanup gelöscht; die Zahlen stehen in `docs/TRAINING.md`. PyTorch/CUDA fehlt hier, daher **kein GPU-Selfplay und kein Starkengine-Beweis**. Für echtes Training den GPU-Befehl oben auf deinem **Heim-PC** laufen lassen — auf dem 2-GB-Laptop ist Training nicht sinnvoll.

Übersicht zum Angucken: `assets/preview/all-preview.png` · Laufzeit-Binärdateien: nur `assets/pieces.zip` + `checkpoints/model.npz`.
