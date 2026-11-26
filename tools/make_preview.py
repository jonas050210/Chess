#!/usr/bin/env python3
"""Erzeugt assets/preview/all-preview.png aus temporären Quellen.

Alle Zwischen-PNGs/SVGs liegen nur in einem TemporaryDirectory und werden gelöscht.
Persistiert werden nur die Gesamtvorschau + ein Xvfb-Fallback-Screenshot.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "assets" / "preview"
OUT = PREVIEW / "all-preview.png"

GREEN = "#58cc02"
GREEN_DARK = "#58a700"
STORY = "#d7ffb8"
BLUE = "#1cb0f6"
NIGHT = "#000437"
CHARCOAL = "#4b4b4b"
GRAY = "#777777"
FADED = "#afafaf"
PAPER = "#ffffff"
POLAR = "#f7f7f7"
BEE = "#ffc800"
RED = "#ff4b4b"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(size: int, bold: bool = False, mono: bool = False):
    name = "DejaVuSansMono-Bold.ttf" if mono and bold else (
        "DejaVuSansMono.ttf" if mono else
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    p = FONT_DIR / name
    try:
        return ImageFont.truetype(str(p), size)
    except Exception:
        return ImageFont.load_default()


F_TITLE = font(38, True)
F_SUB = font(17)
F_CARD = font(16, True)
F_BODY = font(14)
F_SMALL = font(12)
F_MONO = font(13, mono=True)
F_MONO_B = font(13, True, True)


def rr(d, box, fill=PAPER, outline=FADED, width=2, radius=16):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap_px(d, s, f, max_w):
    out, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out or [""]


def label(d, x, y, text, color=GREEN, f=F_CARD):
    d.ellipse((x, y + 3, x + 10, y + 13), fill=color, outline=NIGHT, width=1)
    d.text((x + 18, y), text, font=f, fill=color)


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def paste_fit(canvas: Image.Image, img: Image.Image, box, border=True):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    ratio = min(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    im = img.resize((nw, nh), Image.LANCZOS)
    px, py = x1 + (w - nw) // 2, y1 + (h - nh) // 2
    canvas.paste(im, (px, py))
    if border:
        ImageDraw.Draw(canvas).rounded_rectangle(
            (px - 2, py - 2, px + nw + 2, py + nh + 2),
            radius=10, outline=FADED, width=2)
    return px, py, nw, nh


def build_sources(tmp: Path) -> dict:
    """Erzeugt alle Zwischenbilder temporär; persistiert bleibt nur all-preview.png."""
    subprocess.run([shutil.which("node") or "node",
                    "tools/generate_assets.js", str(tmp)],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/render_assets.py",
                    "--svg-root", str(tmp / "svg"),
                    "--zip-path", str(ROOT / "assets" / "pieces.zip"),
                    "--preview-dir", str(tmp)],
                   cwd=ROOT, check=True)
    shot = tmp / "three-windows-preview.png"
    if shutil.which("xvfb-run"):
        try:
            subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1920x900x24",
                            sys.executable, "tools/capture_ui.py", str(shot)],
                           cwd=ROOT, check=True, timeout=60)
        except Exception as e:
            print("capture failed:", type(e).__name__)
            make_placeholder(tmp, shot)
    else:
        make_placeholder(tmp, shot)
    return {"three": shot, "pieces": tmp / "pieces.png",
            "board": tmp / "board-preview.png"}


def make_placeholder(tmp: Path, shot: Path):
    """Ohne Xvfb: einfaches Board-Platzhalterbild statt persistenter Fallback-Datei."""
    ph = Image.new("RGB", (1920, 900), PAPER)
    b = load(tmp / "board-preview.png").resize((700, 700), Image.LANCZOS)
    ph.paste(b, (610, 100))
    d = ImageDraw.Draw(ph)
    d.text((610, 40), "Xvfb fehlt · auf Ubuntu mit xvfb-run erneut erzeugen",
           font=F_SUB, fill=GRAY)
    ph.save(shot)


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="chess-preview-"))
    src = build_sources(tmp)
    W, H = 1800, 1560
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Header
    d.rectangle((0, 0, W, 8), fill=GREEN)
    d.ellipse((40, 30, 92, 82), fill=STORY, outline=NIGHT, width=3)
    d.text((52, 40), "♟", font=font(34, True), fill=GREEN)
    d.text((112, 28), "Chess Bot v6.2 · Gesamtvorschau", font=F_TITLE, fill=GREEN)
    d.text((114, 76), "Neue Figuren · Drag · Zug-Animation · 1 ZIP · Training nur im Terminal",
           font=F_SUB, fill=GRAY)
    rr(d, (1480, 34, 1760, 82), fill=STORY, outline=NIGHT, width=2, radius=999)
    d.text((1620, 50), "1 PNG · ALLES", font=font(14, True), fill=NIGHT, anchor="mm")

    # Row A — 3 native Fenster
    rr(d, (40, 120, 1200, 790))
    label(d, 60, 138, "3 NATIVE FENSTER · ECHTER XVFB-SCREENSHOT")
    three = load(src["three"])
    paste_fit(img, three, (60, 178, 1180, 730))
    d = ImageDraw.Draw(img)
    d.text((60, 744), "Spiel · Bot & Rewards · Match & Settings · 820/460/340 × 840",
           font=F_SMALL, fill=GRAY)

    # Row A — Figuren + Brett
    rr(d, (1220, 120, 1760, 790))
    label(d, 1240, 138, "NEUE FIGUREN · 12 STICKER")
    pieces = load(src["pieces"])
    paste_fit(img, pieces, (1240, 176, 1740, 390))
    d = ImageDraw.Draw(img)
    label(d, 1240, 406, "BRETT · STORYBOOK-GRÜN")
    board = load(src["board"])
    paste_fit(img, board, (1360, 444, 1620, 744))
    d = ImageDraw.Draw(img)
    d.text((1240, 752), "6 Themes × textured/flat · 144 PNGs in 1 ZIP",
           font=F_SMALL, fill=GRAY)

    # Row B — Browser-Layout-Schema
    rr(d, (40, 810, 900, 1160))
    label(d, 60, 828, "BROWSER-UI · LAYOUT-SCHEMA")
    d.text((60, 856), "Live: http://127.0.0.1:8000 · self-contained HTML · 0 externe Refs",
           font=F_SMALL, fill=GRAY)
    # Mini-Fenster
    rr(d, (60, 884, 880, 1138), fill=POLAR, outline=FADED, width=2, radius=12)
    d.rounded_rectangle((60, 884, 880, 916), radius=12, fill="#e5e5e5", outline=FADED, width=2)
    for i, c in enumerate((RED, BEE, GREEN)):
        d.ellipse((74 + i * 18, 893, 86 + i * 18, 905), fill=c, outline=NIGHT, width=1)
    rr(d, (150, 890, 520, 910), fill=PAPER, outline=FADED, width=1, radius=8)
    d.text((160, 892), "127.0.0.1:8000", font=F_SMALL, fill=GRAY)
    mini = load(src["board"]).resize((220, 220), Image.LANCZOS)
    img.paste(mini, (76, 928))
    d = ImageDraw.Draw(img)
    # Sidebar-Karten
    for i, (t, sub) in enumerate([("STATUS", "playing · Weiß am Zug"),
                                  ("EINSTELLUNGEN", "Theme · Zeit · Textur · Pfeile")]):
        y = 928 + i * 68
        rr(d, (316, y, 864, y + 58), fill=PAPER, outline=FADED, width=2, radius=12)
        d.text((330, y + 8), t, font=font(11, True), fill=GREEN)
        d.text((330, y + 28), sub, font=F_SMALL, fill=GRAY)
    rr(d, (316, 1064, 864, 1104), fill=GREEN, outline=GREEN_DARK, width=2, radius=12)
    d.text((590, 1074), "NEUE PARTIE", font=font(11, True), fill=PAPER)
    d.text((330, 1114), "ANALYSE · PV · Taktik-Chips · FEN/PGN",
           font=F_SMALL, fill=GRAY)

    # Row B — Terminal-Training
    rr(d, (920, 810, 1760, 1160))
    label(d, 940, 828, "TRAINING · NUR TERMINAL")
    d.text((940, 856), "Demo-Lauf · Zahlen aus docs/TRAINING.md",
           font=F_SMALL, fill=GRAY)
    rr(d, (940, 884, 1740, 1138), fill=NIGHT, outline=NIGHT, width=2, radius=12)
    keep = [
        "== Chess-Training v6 · Terminal only ==",
        "run=demo preset=cpu device=cpu torch=False cuda=False",
        "steps=['smoke','tactics'] budget=110s",
        "game 1: 24 Positionen",
        "epoch 60/60 loss=2.0818 samples=197",
        "mate_hit=4/4",
        "ARENA model.npz: +0 =1 -3 score=0.125",
        "ARENA demo.npz: +0 =0 -4 score=0.0",
        "KEINE PROMOTION · no-promote gesetzt",
        "dauer=33.19s · aktiv=model.npz",
    ]
    lines = []
    for l in keep:
        lines.extend(wrap_px(d, l, F_MONO, 770))
    lines = lines[:16]
    y = 898
    for i, l in enumerate(lines):
        col = BEE if ("ARENA" in l or "mate_hit" in l) else (
            STORY if l.startswith("$") or l.startswith("==") else "#ffffff")
        d.text((956, y + i * 15), l, font=F_MONO, fill=col)
    d.text((940, 1144), "Gate schützt model.npz · Kurzlauf ist kein Stärkebeweis",
           font=F_SMALL, fill=GRAY)

    # Row C — Improvements / Cleanup
    rr(d, (40, 1180, 900, 1450))
    label(d, 60, 1198, "IMPROVEMENTS · UMGESETZT")
    items = [
        "Neue Sticker-Figuren: Krone/Kreuz/Turm/Mütze/Pferd/Bauer",
        "Drag mit Ghost + angehobenem Feld in Tk und Browser",
        "Zug-Animation: König, Turm bei Rochade, Promotion",
        "Echt runde Tk-Widgets + ZIEHEN-Header",
        "2-GB-Modus: kleine MCTS, Analyse aus, Poll 1200 ms",
        "Training v6: Kandidaten + Arena-Gate + Report",
    ]
    for i, t in enumerate(items):
        y = 1232 + i * 32
        d.ellipse((62, y + 4, 72, y + 14), fill=GREEN, outline=NIGHT, width=1)
        d.text((84, y), t, font=F_BODY, fill=CHARCOAL)

    rr(d, (920, 1180, 1760, 1450))
    label(d, 940, 1198, "WORKSPACE · CLEANUP & STATUS")
    left = [
        "0 lose Piece-PNGs · 144 Figuren in 1 pieces.zip",
        "Gelöscht: Fallback-PNG, Demo-Log/Report, Root-Starter",
        "Struktur: docs/, assets/preview/, web/ nur index.html",
        "Behalten: 1 wichtiges Preview-PNG + model.npz",
        "Server: Chess Bot v6.2 · Port 8000 · theme=duo",
        "Preview: assets/preview/all-preview.png",
    ]
    for i, t in enumerate(left):
        y = 1232 + i * 32
        d.text((942, y), "✓", font=font(15, True), fill=GREEN)
        d.text((968, y), t, font=F_BODY, fill=CHARCOAL)

    # Footer
    rr(d, (40, 1470, 1760, 1530), fill=GREEN, outline=GREEN_DARK, width=2, radius=16)
    d.text((60, 1488), "Eigene Vektoren · 1 ZIP statt 288 PNGs · Drag + Animation · Training nur im Terminal · kurze Läufe beweisen keine Spielstärke",
           font=font(14, True), fill=PAPER)

    img.save(OUT, optimize=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {OUT} {img.width}x{img.height} {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
