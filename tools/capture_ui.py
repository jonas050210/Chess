#!/usr/bin/env python3
"""Xvfb-Screenshot der 3 Tk-Fenster für die Gesamtvorschau.

Usage (Ubuntu):
  xvfb-run -a -s "-screen 0 1920x900x24" python3 tools/capture_ui.py <out.png>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from PIL import ImageGrab  # noqa: E402


def main_cli():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".preview-tmp" / "three-windows-preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    main.ensure_server()
    app = main.App()
    app.poll_once()
    app.root.update_idletasks()
    app.root.update()

    def finish():
        try:
            if os.name == "nt":
                img = ImageGrab.grab()
            else:
                img = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY"))
            img.save(out)
            print("screenshot", out, img.size)
        except Exception as e:
            print("screenshot_failed", type(e).__name__, str(e)[:120])
        app.quit()

    app.root.after(350, finish)
    app.root.mainloop()


if __name__ == "__main__":
    main_cli()
