#!/usr/bin/env python3
"""Rendert 144 Piece-PNGs in EINE assets/pieces.zip + temporäre Previews.

Keine 288 Einzeldateien, keine _32-Duplikate mehr. main.py lädt die ZIP
direkt via tk.PhotoImage(data=...) und erzeugt 32px mit subsample(2,2).

Usage:
  python3 tools/render_assets.py --svg-root <tmp>/svg \
      --zip-path assets/pieces.zip --preview-dir <tmp>
"""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
DARK = "#a5ed6e"
LIGHT = "#ffffff"


def render_pieces_zip(svg_root: Path, zip_path: Path) -> int:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for src in sorted(svg_root.glob("*/*.svg")):
            variant = src.parent.name
            png = cairosvg.svg2png(url=str(src), output_width=64,
                                   output_height=64)
            z.writestr(f"{variant}/{src.stem}.png", png)
            n += 1
    return n


def piece_from_zip(zip_path: Path, variant: str, name: str):
    with zipfile.ZipFile(zip_path) as z:
        return Image.open(io.BytesIO(z.read(f"{variant}/{name}.png"))).convert("RGBA")


def render_board(zip_path: Path, preview_dir: Path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    board = []
    for row in fen.split()[0].split("/"):
        for ch in row:
            board.extend([None] * int(ch) if ch.isdigit() else [ch])

    s, frame = 64, 20
    w = h = frame * 2 + s * 8
    img = Image.new("RGB", (w, h), LIGHT)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    for r in range(8):
        for c in range(8):
            x1, y1 = frame + c*s, frame + r*s
            x2, y2 = x1+s, y1+s
            f, rank = c, 7-r
            light = (f + rank) % 2 == 1
            d.rectangle((x1, y1, x2, y2), fill=LIGHT if light else DARK,
                        outline="#e5e5e5", width=1)
            if c == 0:
                d.text((x1+3, y1+2), str(rank+1),
                       fill="#58a700" if light else "#000437", font=font)
            if r == 7:
                d.text((x2-12, y2-15), "abcdefgh"[f],
                       fill="#58a700" if light else "#000437", font=font)
            code = board[r*8+c]
            if code:
                name = ("w" if code.isupper() else "b") + code.upper()
                try:
                    piece = piece_from_zip(zip_path, "duo_textured", name)
                    img.paste(piece, (x1, y1), piece)
                except KeyError:
                    pass
    d.rounded_rectangle((4, 4, w-5, h-5), radius=18,
                        outline="#000437", width=3)
    preview_dir.mkdir(parents=True, exist_ok=True)
    img.save(preview_dir / "board-preview.png")
    return w, h


def render_pieces_sheet(preview_dir: Path):
    src = preview_dir / "pieces.svg"
    if src.exists():
        cairosvg.svg2png(url=str(src),
                         write_to=str(preview_dir / "pieces.png"),
                         output_width=672, output_height=264)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg-root", default=str(ROOT / ".preview-tmp" / "svg"))
    ap.add_argument("--zip-path", default=str(ROOT / "assets" / "pieces.zip"))
    ap.add_argument("--preview-dir", default=str(ROOT / ".preview-tmp"))
    a = ap.parse_args()
    svg_root, zip_path, preview = Path(a.svg_root), Path(a.zip_path), Path(a.preview_dir)
    n = render_pieces_zip(svg_root, zip_path)
    w, h = render_board(zip_path, preview)
    render_pieces_sheet(preview)
    print(f"zip={zip_path.name} pieces={n} bytes={zip_path.stat().st_size} board={w}x{h}")


if __name__ == "__main__":
    main()
