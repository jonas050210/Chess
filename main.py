#!/usr/bin/env python3
"""main.py — ein Befehl, drei native Fenster (Windows + Ubuntu).

    Windows:  py main.py
    Ubuntu :  python3 main.py  (tkinter: sudo apt install python3-tk)

Fenster 1: Spiel/Brett
Fenster 2: Bot, Rewards, Reaktion, Analyse, Taktiken
Fenster 3: Zeit, Remis, Settings, Match-Kontrolle

Alle Fenster hängen am selben lokalen Flask-Server auf Port 8000.
v6: Storybook-/Duolingo-inspiriertes Light-Theme als Default, flache Sticker-Figuren,
runde Buttons, Mascot-Badges, Tooltips, Shortcuts, Pfeile/Markierungen, Draw-Offer.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import zipfile
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox
except ImportError:
    print("tkinter fehlt. Ubuntu: sudo apt install python3-tk")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("CHESS_PORT", "8000"))
API = f"http://127.0.0.1:{PORT}"
ASSETS = ROOT / "assets" / "pieces.zip"
S = 64
BOARD_PX = 8 * S

PALETTES = {
    "duo": dict(bg="#ffffff", bg2="#f7f7f7", panel="#ffffff", panel2="#f7f7f7",
                text="#4b4b4b", muted="#777777", line="#afafaf", frame="#58cc02",
                accent="#58cc02", accent_dark="#58a700", light="#ffffff", dark="#a5ed6e",
                coord_light="#58a700", coord_dark="#000437",
                white="#ffffff", black="#4b4b4b",
                night="#000437", last="#ffc800", sel="#ffc800",
                check="#ff4b4b", mark="#1cb0f6"),
    "green": dict(bg="#262522", bg2="#302e2b", panel="#3a3834", panel2="#45423d",
                  text="#f4f2ec", muted="#aaa69b", line="#56524b", frame="#4e7837",
                  accent="#81b64c", accent_dark="#6f9f3e", light="#eeeed2", dark="#769656",
                  coord_light="#769656", coord_dark="#eeeed2",
                  white="#fdfdf8", black="#33322f",
                  last="#d7d59a", sel="#e9e78d", check="#e8534a", mark="#eb3c3c"),
    "brown": dict(bg="#2b2521", bg2="#352c25", panel="#3d342c", panel2="#4a3f35",
                  text="#f8f1e6", muted="#b6a38e", line="#5c4c3d", frame="#8b6343",
                  accent="#c08b5c", accent_dark="#a67549", light="#f0d9b5", dark="#b58863",
                  coord_light="#b58863", coord_dark="#f0d9b5",
                  white="#fff8e8", black="#403226",
                  last="#e8d3ad", sel="#f0dca9", check="#e8534a", mark="#eb3c3c"),
    "blue": dict(bg="#222831", bg2="#28313c", panel="#2f3945", panel2="#3a4654",
                 text="#eef4fa", muted="#9db0c2", line="#4a5868", frame="#3f6d8e",
                 accent="#6fa8c7", accent_dark="#548fb0", light="#e8edf2", dark="#7b9bb8",
                 coord_light="#7b9bb8", coord_dark="#e8edf2",
                 white="#f7fbff", black="#283845",
                 last="#c7d9e8", sel="#b9d2e8", check="#e8534a", mark="#eb3c3c"),
    "midnight": dict(bg="#11161c", bg2="#182028", panel="#202a34", panel2="#2a3642",
                     text="#eef3f8", muted="#9fb0c0", line="#3a4856", frame="#2c3b4a",
                     accent="#5f9ea0", accent_dark="#4a8587", light="#cdd6e0", dark="#6c8199",
                     coord_light="#6c8199", coord_dark="#cdd6e0",
                     white="#f2f6fa", black="#1b2632",
                     last="#a9bccd", sel="#9cb4c9", check="#e8534a", mark="#eb3c3c"),
    "sand": dict(bg="#2f2a22", bg2="#382f24", panel="#40382c", panel2="#4d4335",
                 text="#fbf2df", muted="#c0ab8c", line="#5d4c35", frame="#a07c4f",
                 accent="#d2ab70", accent_dark="#b8915a", light="#f4e3bf", dark="#c39a68",
                 coord_light="#c39a68", coord_dark="#f4e3bf",
                 white="#fff6df", black="#493621",
                 last="#ead6a8", sel="#f0dca8", check="#e8534a", mark="#eb3c3c"),
}
FALLBACK = {"K": "♚", "Q": "♛", "R": "♜", "B": "♝", "N": "♞", "P": "♟"}
PIECE_VALUE = {"P": 1, "N": 3, "B": 3.2, "R": 5, "Q": 9, "K": 0}
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec or 0))
    m, s = int(sec // 60), int(sec % 60)
    if sec < 20:
        return f"{m}:{s:02d}.{int((sec % 1) * 10)}"
    return f"{m}:{s:02d}"


def fen_to_board(fen: str):
    out = []
    for row in fen.split()[0].split("/"):
        for ch in row:
            if ch.isdigit():
                out.extend([None] * int(ch))
            else:
                out.append(ch)
    return out


def piece_key(sym: str, theme: str = "duo", texture: bool = True) -> str:
    """Eintrag in assets/pieces.zip — keine 288 Einzeldateien mehr."""
    color = "w" if sym.isupper() else "b"
    variant = f"{theme}_{'textured' if texture else 'flat'}"
    return f"{variant}/{color}{sym.upper()}.png"


class Api:
    def __init__(self, base: str):
        self.base = base
        self.offline = False

    def _call(self, path: str, payload=None):
        url = self.base + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as r:
                self.offline = False
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            self.offline = True
            return {"error": str(e)}

    def get(self, path: str):
        return self._call(path)

    def post(self, path: str, payload=None):
        return self._call(path, payload if payload is not None else {})


def ensure_server() -> bool:
    try:
        urllib.request.urlopen(API + "/api/state", timeout=0.5).read()
        return True
    except Exception:
        pass
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    kwargs = {"cwd": str(ROOT), "env": env,
              "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen([sys.executable, str(ROOT / "server.py")], **kwargs)
    except Exception as e:
        print("Server konnte nicht gestartet werden:", e)
        return False
    for _ in range(40):
        try:
            urllib.request.urlopen(API + "/api/state", timeout=0.5).read()
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _rounded_shape(canvas, x1, y1, x2, y2, r, color):
    """Gefüllte Rounded-Rect-Form aus 4 Arcs + 2 Rectangles (Tk hat kein Antialiasing)."""
    r = max(1, min(int(r), (x2 - x1) // 2, (y2 - y1) // 2))
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline="")
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline="")
    canvas.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90, extent=90,
                      fill=color, outline="")
    canvas.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0, extent=90,
                      fill=color, outline="")
    canvas.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90,
                      fill=color, outline="")
    canvas.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90,
                      fill=color, outline="")


def round_rect(canvas, x1, y1, x2, y2, r=12, fill="#ffffff",
               outline="#afafaf", width=2):
    """Runder Rahmen ohne pixeliges Polygon: außen Outline, innen Fill."""
    _rounded_shape(canvas, x1, y1, x2, y2, r, outline)
    _rounded_shape(canvas, x1 + width, y1 + width, x2 - width, y2 - width,
                   max(1, r - width), fill)
    return None


class RoundedFrame(tk.Frame):
    """Frame mit wirklich abgerundeter Canvas-Umrandung; Kinder liegen darüber."""

    def __init__(self, parent, ui, radius=16, fill="panel", outline="line", **kw):
        p = ui.app.palette
        super().__init__(parent, bg=p[fill], **kw)
        self.ui, self.radius, self.fill_key, self.outline_key = ui, radius, fill, outline
        self.canvas = tk.Canvas(self, bg=p["bg"], highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.canvas._role = ("canvas", "bg")
        self.bind("<Configure>", lambda _e: self.redraw())
        self.redraw()

    def redraw(self):
        p = self.ui.app.palette
        self.configure(bg=p[self.fill_key])
        self.canvas.configure(bg=p["bg"])
        self.canvas.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w > 4 and h > 4:
            round_rect(self.canvas, 1, 1, w - 2, h - 2, self.radius,
                       fill=p[self.fill_key], outline=p[self.outline_key], width=2)
        tk.Misc.lower(self.canvas)


def make_draggable(win, *handles):
    """Fenster auch ohne Window-Manager-Decorations am Header ziehen."""
    def collect(w):
        out = [w]
        for c in w.winfo_children():
            out.extend(collect(c))
        return out
    for handle in handles:
        for t in collect(handle):
            try:
                t.configure(cursor="fleur")
                t.bind("<ButtonPress-1>",
                       lambda e, w=win: setattr(w, "_drag", (e.x_root - w.winfo_x(),
                                                             e.y_root - w.winfo_y())),
                       add="+")
                t.bind("<B1-Motion>",
                       lambda e, w=win: w.wm_geometry(
                           f"+{e.x_root - w._drag[0]}+{e.y_root - w._drag[1]}")
                       if hasattr(w, "_drag") else None, add="+")
                t.bind("<ButtonRelease-1>",
                       lambda e, w=win: delattr(w, "_drag")
                       if hasattr(w, "_drag") else None, add="+")
            except Exception:
                pass


class StickerButton(tk.Canvas):
    """Runder, flacher Storybook-Button mit 2px Outline und 4px Lip."""

    def __init__(self, parent, text, command, ui, accent=False, image=None, **kw):
        kw.setdefault("width", 120)
        kw.setdefault("height", 38)
        super().__init__(parent, bg=ui.p["panel"], highlightthickness=0, bd=0, **kw)
        self.ui, self.text, self.command, self.accent = ui, text, command, accent
        self.image = image
        self.hover = False
        self.pressed = False
        self._last_size = (0, 0)
        self.configure(cursor="hand2")
        self.bind("<Enter>", lambda _e: self._set(True, self.pressed), add="+")
        self.bind("<Leave>", lambda _e: self._set(False, False), add="+")
        self.bind("<ButtonPress-1>", lambda _e: self._set(self.hover, True), add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Configure>", self._resize, add="+")
        self.redraw()

    def _set(self, hover, pressed):
        if (hover, pressed) != (self.hover, self.pressed):
            self.hover, self.pressed = hover, pressed
            self.redraw()

    def _release(self, _event):
        was = self.pressed
        self._set(self.hover, False)
        if was and self.command:
            self.command()

    def _resize(self, _event):
        size = (self.winfo_width(), self.winfo_height())
        if size != self._last_size:
            self._last_size = size
            self.redraw()

    def redraw(self):
        p = self.ui.app.palette
        w = max(20, self.winfo_width() or int(self.cget("width")))
        h = max(20, self.winfo_height() or int(self.cget("height")))
        r = 12
        lip = 4
        self.delete("all")
        self.configure(bg=p["panel"])
        lip_color = p["accent_dark"] if self.accent else p["line"]
        if self.accent:
            fill = p["accent_dark"] if (self.hover or self.pressed) else p["accent"]
            fg = "#ffffff"
            outline = p["accent_dark"]
        else:
            fill = p["panel2"] if self.hover else p["panel"]
            fg = p["text"]
            outline = p["accent"] if self.hover else p["line"]
        y1 = 2 + (lip if self.pressed else 0)
        y2 = h - 2 - (0 if self.pressed else lip)
        if not self.pressed:
            _rounded_shape(self, 2, 2 + lip, w - 2, h - 2 + lip, r, lip_color)
        round_rect(self, 2, y1, w - 2, y2, r,
                   fill=fill, outline=outline, width=2)
        if self.image is not None:
            self.create_image(w / 2, (y1 + y2) / 2, image=self.image)
        else:
            self.create_text(w / 2, (y1 + y2) / 2, text=self.text, fill=fg,
                             font=(self.ui.app.font, 10, "bold"))


class Mascot(tk.Canvas):
    """Kleiner eigener Pawn-Sticker, kein Duo/Owl-Asset."""

    def __init__(self, parent, ui, size=42):
        super().__init__(parent, width=size, height=size,
                         bg=ui.p["bg"], highlightthickness=0, bd=0)
        self.ui, self.size = ui, size
        self.redraw()

    def redraw(self):
        p = self.ui.app.palette
        s = self.size
        night = p.get("night", p["black"])
        self.configure(bg=p["bg"])
        self.delete("all")
        self.create_oval(2, 2, s-2, s-2, fill=p["panel2"], outline=night, width=2)
        body = [s*.30,s*.72, s*.70,s*.72, s*.74,s*.42,
                s*.50,s*.22, s*.26,s*.42]
        self.create_polygon(body, smooth=True, splinesteps=36,
                            fill=p["accent"], outline=night, width=3)
        self.create_oval(s*.36,s*.42,s*.40,s*.46, fill=night, outline="")
        self.create_oval(s*.60,s*.42,s*.64,s*.46, fill=night, outline="")
        self.create_arc(s*.38,s*.47,s*.62,s*.64, start=200, extent=140,
                        style="arc", outline=night, width=2)
        self.create_oval(s*.25,s*.52,s*.30,s*.57, fill=p["mark"], outline="")
        self.create_oval(s*.70,s*.52,s*.75,s*.57, fill=p["mark"], outline="")


class ToolTip:
    """Kleines, theme-farbiges Hilfefenster für Buttons."""

    def __init__(self, widget, text, app):
        self.widget, self.text, self.app, self.tip = widget, text, app, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.tip is not None:
            return
        w = self.widget
        x = w.winfo_rootx() + 12
        y = w.winfo_rooty() + w.winfo_height() + 5
        p = self.app.palette
        self.tip = tk.Toplevel(w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg=p["panel2"], fg=p["text"],
                 relief="solid", bd=1, padx=7, pady=3,
                 font=(self.app.font, 9, "bold")).pack()

    def hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class UI:
    """Kleiner Helper für Theme-Rollen an tk-Widgets."""

    def __init__(self, app):
        self.app = app

    @property
    def p(self):
        return self.app.palette

    def _role(self, w, role):
        try:
            w._role = role
        except Exception:
            pass
        return w

    def frame(self, parent, key="panel", **kw):
        return self._role(tk.Frame(parent, bg=self.p[key], **kw), ("frame", key))

    def card(self, parent, **kw):
        return RoundedFrame(parent, self, radius=16, fill="panel", outline="line", **kw)

    def label(self, parent, text="", fg="text", bg="panel", size=10, bold=False, **kw):
        f = (self.app.font, size, "bold" if bold else "normal")
        return self._role(tk.Label(parent, text=text, bg=self.p[bg], fg=self.p[fg],
                                   font=f, **kw), ("label", fg, bg))

    def button(self, parent, text, command=None, accent=False, tooltip=None, image=None, **kw):
        b = StickerButton(parent, text, command, self, accent=accent, image=image, **kw)
        if tooltip:
            ToolTip(b, tooltip, self.app)
        return self._role(b, ("button", accent))

    def check(self, parent, text, variable, command=None):
        wrap = RoundedFrame(parent, self, radius=12, fill="panel", outline="line")
        cb = tk.Checkbutton(wrap, text=text, variable=variable, command=command,
                            bg=self.p["panel"], fg=self.p["text"],
                            selectcolor=self.p["panel2"],
                            activebackground=self.p["panel"],
                            activeforeground=self.p["text"],
                            relief="flat", bd=0, highlightthickness=0,
                            font=(self.app.font, 10))
        cb.pack(padx=7, pady=2)
        self._role(cb, ("check", "panel"))
        return wrap

    def option(self, parent, variable, values, command=None):
        wrap = RoundedFrame(parent, self, radius=12, fill="panel", outline="line")
        w = tk.OptionMenu(wrap, variable, *values, command=command)
        w.configure(bg=self.p["panel"], fg=self.p["text"],
                    activebackground=self.p["panel2"], highlightthickness=0,
                    relief="flat", bd=0, font=(self.app.font, 10), width=12)
        m = w["menu"]
        m.configure(bg=self.p["panel2"], fg=self.p["text"],
                    activebackground=self.p["accent"], activeforeground="#14210c",
                    font=(self.app.font, 10))
        w.pack(fill="x", expand=True, padx=6, pady=2)
        self._role(w, ("option", "panel2"))
        return wrap

    def spin(self, parent, from_, to, variable, command=None, width=6):
        wrap = RoundedFrame(parent, self, radius=12, fill="panel", outline="line")
        w = tk.Spinbox(wrap, from_=from_, to=to, textvariable=variable,
                       command=command, bg=self.p["panel"], fg=self.p["text"],
                       buttonbackground=self.p["panel2"],
                       insertbackground=self.p["text"],
                       relief="flat", bd=0, highlightthickness=0,
                       font=(self.app.font, 10), width=width)
        w.pack(fill="x", expand=True, padx=6, pady=2)
        self._role(w, ("spin", "panel2"))
        return wrap

    def canvas(self, parent, key="frame", **kw):
        return self._role(tk.Canvas(parent, bg=self.p[key], highlightthickness=0, **kw),
                          ("canvas", key))

    def text(self, parent, key="bg", **kw):
        frame = RoundedFrame(parent, self, radius=12, fill=key, outline="line")
        frame.pack(fill="both", expand=True)
        t = tk.Text(frame, bg=self.p[key], fg=self.p["text"],
                    insertbackground=self.p["text"], relief="flat", bd=0,
                    highlightthickness=0, font=("Consolas", 9), **kw)
        self._role(t, ("text", key))
        return t

    def apply(self, widget):
        p = self.p
        for w in widget.winfo_children():
            if hasattr(w, "redraw"):
                try:
                    w.redraw()
                except Exception:
                    pass
                self.apply(w)
                continue
            role = getattr(w, "_role", None)
            try:
                if role and role[0] == "frame":
                    w.configure(bg=p[role[1]])
                elif role and role[0] == "card":
                    w.configure(bg=p["panel"], highlightbackground=p["line"],
                                highlightthickness=2 if self.app.theme_name == "duo" else 1)
                elif role and role[0] == "label":
                    w.configure(bg=p[role[2]], fg=p[role[1]])
                elif role and role[0] == "button":
                    accent = role[1]
                    w.configure(bg=p["accent"] if accent else p["panel2"],
                                fg="#14210c" if accent else p["text"],
                                activebackground=p["accent_dark"] if accent else p["line"])
                elif role and role[0] == "check":
                    w.configure(bg=p["panel"], fg=p["text"],
                                selectcolor=p["panel2"],
                                activebackground=p["panel"], activeforeground=p["text"],
                                relief="flat", bd=0, highlightthickness=0)
                elif role and role[0] == "option":
                    w.configure(bg=p["panel"], fg=p["text"],
                                activebackground=p["panel2"],
                                relief="flat", bd=0, highlightthickness=0)
                    w["menu"].configure(bg=p["panel2"], fg=p["text"],
                                        activebackground=p["accent"],
                                        activeforeground="#14210c")
                elif role and role[0] == "spin":
                    w.configure(bg=p["panel"], fg=p["text"],
                                buttonbackground=p["panel2"],
                                insertbackground=p["text"],
                                relief="flat", bd=0, highlightthickness=0)
                elif role and role[0] == "canvas":
                    w.configure(bg=p[role[1]])
                elif role and role[0] == "text":
                    w.configure(bg=p[role[1]], fg=p["text"],
                                insertbackground=p["text"],
                                relief="flat", bd=0, highlightthickness=0)
            except Exception:
                pass
            self.apply(w)


class GameWindow(tk.Tk):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ui = UI(app)
        self.title("Chess · Spiel")
        self.configure(bg=app.palette["bg"])
        self.resizable(False, False)
        self.state_data = None
        self.board_arr = fen_to_board(START_FEN)
        self.images = {}
        self.cap_images = {}
        self.asset_theme = app.theme_name
        self.asset_texture = bool((app.last_state or {}).get("settings", {}).get("texture", True))
        self.hover_sq = None
        self.marks = set()
        self.arrows = []
        self.arrow_start = None
        self.arrows_enabled = True
        self.animation_on = True
        self.last_seen_fen = None
        self.last_seen_move = None
        self.anim_hide = set()
        self.animating = False
        self.anim_items = []
        self.anim_job = None
        self.anim_step = 0
        self.anim_total = 10
        self.load_images()
        self.selected = None
        self.premove_mode = False
        self.drag = None
        self.flip = False
        self.coords_on = True
        self.auto_queen = False
        self.premove_enabled = True
        self.last_draw_key = None
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.app.quit)
        self.bind("<F11>", lambda e: self.toggle_flip())

    def load_images(self, theme=None, texture=None):
        if theme is not None:
            self.asset_theme = theme if theme in PALETTES else "duo"
        if texture is not None:
            self.asset_texture = bool(texture)
        self.images.clear()
        self.cap_images.clear()
        if not ASSETS.exists():
            return
        try:
            with zipfile.ZipFile(ASSETS) as z:
                names = set(z.namelist())
                for sym in "KQRBNPkqrbnp":
                    keys = [piece_key(sym, self.asset_theme, self.asset_texture),
                            piece_key(sym, "duo", self.asset_texture),
                            piece_key(sym, "duo", True)]
                    data = next((z.read(k) for k in keys if k in names), None)
                    if data is None:
                        self.images[sym] = self.cap_images[sym] = None
                        continue
                    img = tk.PhotoImage(master=self,
                                        data=base64.b64encode(data).decode("ascii"))
                    self.images[sym] = img
                    self.cap_images[sym] = img.subsample(2, 2)  # 32px on-the-fly
        except Exception as e:
            print("Piece-Zip:", e)
            for sym in "KQRBNPkqrbnp":
                self.images[sym] = self.cap_images[sym] = None

    def build(self):
        p = self.app.palette
        outer = self.ui.frame(self, "bg")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        header = self.ui.frame(outer, "bg")
        header.pack(side="top", fill="x", pady=(0, 4))
        Mascot(header, self.ui, 38).pack(side="left", padx=(0, 7))
        self.ui.label(header, "SPIEL", fg="accent", bg="bg", size=13, bold=True).pack(side="left")
        self.ui.label(header, "Storybook · flache Sticker-Figuren", fg="muted", bg="bg", size=9).pack(side="right")
        self.ui.label(header, "⋮⋮ ZIEHEN", fg="muted", bg="bg", size=8, bold=True).pack(side="right", padx=(0, 10))
        make_draggable(self, header)
        left = self.ui.frame(outer, "bg")
        left.pack(side="left", fill="y")
        self.eval_canvas = self.ui.canvas(left, "bg", width=18, height=BOARD_PX)
        self.eval_canvas.pack(side="left", fill="y", padx=(0, 6))
        bf = self.ui.frame(left, "frame")
        bf.pack(side="left")
        self.canvas = self.ui.canvas(bf, "frame", width=BOARD_PX, height=BOARD_PX)
        self.canvas.pack(padx=8, pady=8)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        self.ghost = self.canvas.create_image(-100, -100, state="hidden")

        right = self.ui.frame(outer, "bg", width=220)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        right.pack_propagate(False)
        self.top_bar = self.ui.card(right)
        self.top_bar.pack(fill="x", pady=(0, 8))
        self.top_name = self.ui.label(self.top_bar, "Lokale KI", bold=True, size=11)
        self.top_name.pack(anchor="w", padx=10, pady=(8, 2))
        self.top_cap = self.ui.canvas(self.top_bar, "panel", height=26)
        self.top_cap.pack(fill="x", padx=10, pady=(0, 4))
        self.top_clock = self.ui.label(self.top_bar, "10:00", fg="accent", size=16, bold=True)
        self.top_clock.pack(anchor="e", padx=10, pady=(0, 8))

        self.status = self.ui.label(right, "lädt…", fg="text", bg="bg", size=11, bold=True)
        self.status.pack(fill="x", pady=(0, 6))
        self.meta = self.ui.label(right, "", fg="muted", bg="bg", size=9,
                                  wraplength=210, justify="left")
        self.meta.pack(fill="x", pady=(0, 6))

        ml = self.ui.card(right)
        ml.pack(fill="both", expand=True)
        self.ui.label(ml, "ZÜGE", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(8, 2))
        self.moves = self.ui.text(ml, "panel", height=10, width=24, wrap="none")
        self.moves.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.fen = self.ui.label(ml, "", fg="muted", size=8, wraplength=200, justify="left")
        self.fen.pack(fill="x", padx=8, pady=(0, 8))

        self.bottom_bar = self.ui.card(right)
        self.bottom_bar.pack(fill="x", pady=(8, 0))
        self.bottom_name = self.ui.label(self.bottom_bar, "Du", bold=True, size=11)
        self.bottom_name.pack(anchor="w", padx=10, pady=(8, 2))
        self.bottom_cap = self.ui.canvas(self.bottom_bar, "panel", height=26)
        self.bottom_cap.pack(fill="x", padx=10, pady=(0, 4))
        self.bottom_clock = self.ui.label(self.bottom_bar, "10:00", fg="accent", size=16, bold=True)
        self.bottom_clock.pack(anchor="e", padx=10, pady=(0, 8))

    # ---------- Koordinaten ----------
    def view_to_square(self, r, c):
        f = 7 - c if self.flip else c
        rank = r if self.flip else 7 - r
        return "abcdefgh"[f] + str(rank + 1)

    def square_to_view(self, sq):
        f = "abcdefgh".index(sq[0]); rank = int(sq[1]) - 1
        c = 7 - f if self.flip else f
        r = rank if self.flip else 7 - rank
        return r, c

    def sq_to_index(self, sq):
        f = "abcdefgh".index(sq[0]); rank = int(sq[1]) - 1
        return (7 - rank) * 8 + f

    def square_center(self, sq):
        r, c = self.square_to_view(sq)
        return c * S + S / 2, r * S + S / 2

    def move_parts(self, uci):
        mv = (uci or "")[:4]
        if len(mv) < 4:
            return []
        frm, to = mv[:2], mv[2:4]
        parts = [(frm, to)]
        if frm[0] == "e" and frm[1] in "18" and to[0] in "gc":
            rank = frm[1]
            parts.append((f"h{rank}", f"f{rank}") if to[0] == "g"
                         else (f"a{rank}", f"d{rank}"))
        return parts

    def _finish_animation(self, redraw=True):
        if self.anim_job is not None:
            try:
                self.after_cancel(self.anim_job)
            except Exception:
                pass
            self.anim_job = None
        for item, *_ in self.anim_items:
            try:
                self.canvas.delete(item)
            except Exception:
                pass
        self.anim_items = []
        self.animating = False
        self.anim_hide.clear()
        if redraw and self.state_data:
            self.draw_board()

    def _animate_tick(self):
        if not self.animating:
            return
        self.anim_step += 1
        t = min(1.0, self.anim_step / self.anim_total)
        ease = 1 - (1 - t) ** 3
        for item, x1, y1, x2, y2 in self.anim_items:
            self.canvas.coords(item, x1 + (x2 - x1) * ease,
                               y1 + (y2 - y1) * ease)
        if t < 1.0:
            self.anim_job = self.after(18, self._animate_tick)
        else:
            self.anim_job = None
            self._finish_animation()

    def _start_move_animation(self, old_fen, uci):
        if not old_fen:
            return
        old_board = fen_to_board(old_fen)
        items = []
        for frm, to in self.move_parts(uci):
            try:
                code = old_board[self.sq_to_index(frm)]
            except (ValueError, IndexError):
                continue
            img = self.images.get(code) if code else None
            if img is None:
                continue
            x1, y1 = self.square_center(frm)
            x2, y2 = self.square_center(to)
            item = self.canvas.create_image(x1, y1, image=img)
            items.append((item, x1, y1, x2, y2))
        if not items:
            self.anim_hide.clear()
            self.draw_board()
            return
        self.anim_items = items
        self.anim_step = 0
        self.anim_total = 8 if self.app.low else 11
        self.animating = True
        self._animate_tick()

    def code_at(self, sq):
        return self.board_arr[self.sq_to_index(sq)]

    def all_squares(self):
        return [f + str(r) for f in "abcdefgh" for r in range(1, 9)]

    def legal_targets(self, frm):
        st = self.state_data or {}
        if self.premove_mode:
            return [s for s in self.all_squares() if s != frm]
        return [m[2:4] for m in st.get("legal", []) if m.startswith(frm)]

    # ---------- Zeichnen ----------
    def draw_board(self):
        if not self.state_data:
            return
        p = self.app.palette
        st = self.state_data
        self.board_arr = fen_to_board(st.get("fen", START_FEN))
        c = self.canvas
        c.delete("all")
        lf = (st.get("last_move") or "")[:2]
        lt = (st.get("last_move") or "")[2:4]
        pm = st.get("premove") or ""
        pm_from, pm_to = pm[:2], pm[2:4]
        check_sq = st.get("check_square")
        for r in range(8):
            for col in range(8):
                sq = self.view_to_square(r, col)
                f = "abcdefgh".index(sq[0]); rank = int(sq[1]) - 1
                light = (f + rank) % 2 == 1
                x1, y1 = col * S, r * S
                x2, y2 = x1 + S, y1 + S
                c.create_rectangle(x1, y1, x2, y2, fill=p["light"] if light else p["dark"], outline="")
                if sq in (lf, lt):
                    c.create_rectangle(x1, y1, x2, y2, fill=p["last"], stipple="gray50", outline="")
                if sq == self.selected:
                    c.create_rectangle(x1, y1, x2, y2, fill=p["sel"], stipple="gray50", outline="")
                if sq == check_sq:
                    c.create_oval(x1 + 8, y1 + 8, x2 - 8, y2 - 8, outline=p["check"], width=4)
                if sq in self.marks:
                    c.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3,
                                       outline=p["mark"], width=3)
                if sq in (pm_from, pm_to):
                    c.create_rectangle(x1 + 4, y1 + 4, x2 - 4, y2 - 4,
                                       outline=p["mark"], width=2, dash=(5, 3))
                if sq == self.hover_sq:
                    c.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y2 - 2,
                                       outline=p["accent"], width=2)
                if self.coords_on:
                    cc = p["coord_light"] if light else p["coord_dark"]
                    if col == 0:
                        c.create_text(x1 + 4, y1 + 10, text=str(rank + 1), fill=cc,
                                      anchor="nw", font=("Segoe UI", 8, "bold"))
                    if r == 7:
                        c.create_text(x2 - 4, y2 - 3, text="abcdefgh"[f], fill=cc,
                                      anchor="se", font=("Segoe UI", 8, "bold"))
                lift = bool(self.drag and self.drag.get("from") == sq)
                if lift:
                    round_rect(c, x1 + 6, y1 + 6, x2 - 6, y2 - 6, 12,
                               fill=p["sel"], outline=p["accent"], width=2)
                code = self.code_at(sq)
                if code and not lift and sq not in self.anim_hide:
                    img = self.images.get(code)
                    if img is not None:
                        c.create_image(x1 + S / 2, y1 + S / 2, image=img)
                    else:
                        fg = p["white"] if code.isupper() else p["black"]
                        c.create_text(x1 + S / 2, y1 + S / 2 + 2, text=FALLBACK[code.upper()],
                                      fill=fg, font=("DejaVu Sans", int(S * 0.72)))
                if self.selected and sq in self.legal_targets(self.selected) and sq != self.selected:
                    if code:
                        c.create_oval(x1 + 6, y1 + 6, x2 - 6, y2 - 6,
                                      outline="#23221f", width=4)
                    else:
                        c.create_oval(x1 + S * .38, y1 + S * .38,
                                      x2 - S * .38, y2 - S * .38,
                                      fill="#23221f", stipple="gray50", outline="")
        def center(sq):
            r, col = self.square_to_view(sq)
            return col * S + S / 2, r * S + S / 2
        if lf and lt:
            x1, y1 = center(lf)
            x2, y2 = center(lt)
            c.create_line(x1, y1, x2, y2, fill=p["sel"], width=6,
                          stipple="gray50", arrow=tk.LAST, arrowshape=(12, 14, 5))
        for src, dst in self.arrows:
            x1, y1 = center(src)
            x2, y2 = center(dst)
            c.create_line(x1, y1, x2, y2, fill=p["mark"], width=4,
                          arrow=tk.LAST, arrowshape=(10, 12, 4))
        self.ghost = c.create_image(-100, -100, state="hidden")

    def draw_eval(self, material, cp=None):
        p = self.app.palette
        c = self.eval_canvas
        c.delete("all")
        h = BOARD_PX
        val = (cp / 100.0) if cp is not None else float(material or 0)
        pct = max(2, min(98, 50 + 48 * math.tanh(val / 4.0)))
        y = h * (1 - pct / 100)
        c.create_rectangle(0, 0, 18, h, fill=p["panel2"], outline="")
        c.create_rectangle(0, y, 18, h, fill=p["accent"], outline="")
        label = "M" if abs(cp or 0) > 90000 else f"{val:+.1f}"
        c.create_text(9, h - 10, text=label, fill=p["text"], angle=90,
                      font=("Segoe UI", 8, "bold"))

    def draw_captured(self, canvas, syms, diff=0.0):
        p = self.app.palette
        canvas.delete("all")
        canvas.configure(bg=p["panel"])
        x = 2
        for sym in syms[:12]:
            img = self.cap_images.get(sym)
            if img is not None:
                canvas.create_image(x + 9, 13, image=img)
            else:
                fg = p["white"] if sym.isupper() else p["black"]
                canvas.create_text(x + 9, 13, text=FALLBACK[sym.upper()], fill=fg,
                                   font=("DejaVu Sans", 14))
            x += 17
        if diff:
            w = canvas.winfo_width()
            if w < 20:
                w = 220
            canvas.create_text(w - 4, 13, text=f"+{diff:g}", anchor="e",
                               fill=p["accent"], font=("Segoe UI", 9, "bold"))

    def update_data(self, state, stats, analysis):
        if "error" in state:
            self.status.configure(text="Server offline")
            return
        old = self.state_data
        old_fen = old.get("fen") if old else None
        old_move = old.get("last_move") if old else None
        old_san_len = len(old.get("san", [])) if old else 0
        new_fen = state.get("fen")
        new_move = state.get("last_move")
        new_san_len = len(state.get("san", []))
        if self.animating:
            self._finish_animation(redraw=False)
        self.state_data = state
        settings = state.get("settings", {})
        self.flip = bool(settings.get("flip", self.flip))
        self.coords_on = bool(settings.get("coords", True))
        self.auto_queen = bool(settings.get("auto_queen", False))
        self.premove_enabled = bool(settings.get("premove", True))
        self.arrows_enabled = bool(settings.get("arrows", True))
        texture = bool(settings.get("texture", True))
        if texture != self.asset_texture:
            self.load_images(self.app.theme_name, texture)
        match = getattr(self.app, "match", None)
        anim_setting = bool(settings.get("animation", True))
        if match is not None and not bool(match.animation.get()):
            anim_setting = False
        self.animation_on = anim_setting and not self.app.low
        p = self.app.palette
        top_color = "w" if self.flip else "b"
        bottom_color = "b" if self.flip else "w"
        you = state.get("you_color", "w")
        top_t = state["clocks"].get(top_color, 0)
        bottom_t = state["clocks"].get(bottom_color, 0)
        self.top_name.configure(text=("Du" if top_color == you else "Lokale KI"))
        self.bottom_name.configure(text=("Du" if bottom_color == you else "Lokale KI"))
        self.top_clock.configure(text=fmt_time(top_t),
                                 fg=p["check"] if top_t < 30 else p["accent"])
        self.bottom_clock.configure(text=fmt_time(bottom_t),
                                    fg=p["check"] if bottom_t < 30 else p["accent"])
        cap_top = state["captured"].get(top_color, [])
        cap_bottom = state["captured"].get(bottom_color, [])
        value = lambda xs: sum(PIECE_VALUE.get(s.upper(), 0) for s in xs)
        diff_top = value(cap_top) - value(cap_bottom)
        self.draw_captured(self.top_cap, cap_top, diff_top)
        self.draw_captured(self.bottom_cap, cap_bottom, -diff_top)

        status = state.get("status", "?")
        txt = ("Weiß am Zug" if state.get("turn") == "w" else "Schwarz am Zug")
        if state.get("bot_thinking"):
            txt = "KI denkt …"
        if status not in ("playing", "check"):
            txt = status + ("" if not state.get("winner") else f" · {state['winner']} gewinnt")
        if state.get("check"):
            txt += " · Schach!"
        offer = state.get("draw_offer")
        if offer == "declined":
            txt += " · Remis abgelehnt"
        elif offer == "pending":
            txt += " · Remis offen"
        self.status.configure(text=txt)
        r = state.get("rules", {})
        inc = state.get("increment", 0)
        pm = state.get("premove")
        self.meta.configure(text=(f"{r.get('phase','—')} · Material {r.get('material_balance',0):+.1f} · "
                                  f"+{inc:g}s · Zug {state.get('last_move_ms',0):.0f} ms · "
                                  f"Premove: {pm or '—'}"))
        san = state.get("san", [])
        rows = []
        for i in range(0, len(san), 2):
            rows.append(f"{i//2+1:>2}. {san[i]:<8} {san[i+1] if i+1 < len(san) else ''}")
        shown = rows[-14:]
        self.moves.tag_configure("last", background=p["panel2"], foreground=p["accent"])
        self.moves.configure(state="normal")
        self.moves.delete("1.0", "end")
        for i, row in enumerate(shown):
            self.moves.insert("end", row + ("\n" if i + 1 < len(shown) else ""),
                              ("last",) if i + 1 == len(shown) else ())
        self.moves.configure(state="disabled")
        self.fen.configure(text=state.get("fen", "")[:46] + "…")
        cp = None
        if analysis and analysis.get("fen") == state.get("fen") and analysis.get("result"):
            cp = analysis["result"].get("eval_white")
        should_animate = bool(
            self.animation_on and old_fen and new_fen != old_fen and new_move
            and new_move != old_move and new_san_len >= old_san_len)
        self.anim_hide = {to for _, to in self.move_parts(new_move)} if should_animate else set()
        self.draw_board()
        self.draw_eval(r.get("material_balance", 0), cp)
        if should_animate:
            self._start_move_animation(old_fen, new_move)
        self.last_draw_key = new_fen
        self.last_seen_fen = new_fen
        self.last_seen_move = new_move

    def on_theme(self):
        self.configure(bg=self.app.palette["bg"])
        self.load_images(self.app.theme_name, self.asset_texture)
        self.moves.tag_configure("last", background=self.app.palette["panel2"],
                                 foreground=self.app.palette["accent"])
        if self.state_data:
            self.update_data(self.state_data, {}, {})

    # ---------- Eingabe ----------
    def event_square(self, event):
        col = max(0, min(7, event.x // S))
        r = max(0, min(7, event.y // S))
        return self.view_to_square(r, col)

    def my_turn(self):
        st = self.state_data or {}
        return (not st.get("bot_enabled")) or st.get("turn") == st.get("you_color")

    def can_premove(self):
        st = self.state_data or {}
        return bool(self.premove_enabled and st.get("bot_thinking") and not self.my_turn())

    def on_press(self, event):
        if self.animating:
            self._finish_animation(redraw=False)
        st = self.state_data or {}
        if st.get("status") not in ("playing", "check"):
            return
        sq = self.event_square(event)
        if self.selected and sq in self.legal_targets(self.selected):
            frm = self.selected
            self.selected = None
            self.try_move(frm, sq)
            self.draw_board()
            return
        code = self.code_at(sq)
        pm = self.can_premove()
        if not code:
            self.selected = None
            self.premove_mode = False
            self.draw_board()
            return
        color = "w" if code.isupper() else "b"
        allowed = (color == st.get("turn")) if not pm else (color == st.get("you_color"))
        if not allowed:
            self.selected = None
            self.premove_mode = False
            self.draw_board()
            return
        self.selected = sq
        self.premove_mode = pm
        self.drag = {"from": sq, "code": code}
        self.draw_board()  # hebt die Figur aus dem Feld, erzeugt neuen Ghost
        img = self.images.get(code)
        if img is not None:
            self.canvas.itemconfigure(self.ghost, image=img, state="normal")
            self.canvas.coords(self.ghost, event.x, event.y)
            self.canvas.tag_raise(self.ghost)

    def on_motion(self, event):
        if self.drag:
            self.canvas.coords(self.ghost, event.x, event.y)
            self.canvas.tag_raise(self.ghost)

    def on_release(self, event):
        if not self.drag:
            return
        frm = self.drag["from"]
        self.drag = None
        sq = self.event_square(event)
        if sq != frm and sq in self.legal_targets(frm):
            self.selected = None
            self.try_move(frm, sq)
        else:
            self.selected = frm if sq == frm else self.selected
        self.draw_board()

    def on_hover(self, event):
        if self.drag or self.animating or not self.state_data:
            return
        sq = self.event_square(event)
        if sq != self.hover_sq:
            self.hover_sq = sq
            self.draw_board()

    def on_right_press(self, event):
        self.arrow_start = self.event_square(event)

    def on_right_release(self, event):
        sq = self.event_square(event)
        start = self.arrow_start
        self.arrow_start = None
        if start == sq or not self.arrows_enabled:
            if sq in self.marks:
                self.marks.remove(sq)
            else:
                self.marks.add(sq)
        else:
            pair = (start, sq)
            if pair in self.arrows:
                self.arrows.remove(pair)
            else:
                self.arrows.append(pair)
                self.arrows = self.arrows[-12:]
        self.draw_board()

    def clear_marks(self):
        self.marks.clear()
        self.arrows.clear()
        self.arrow_start = None
        if self.state_data:
            self.draw_board()

    def cancel_premove(self):
        self.premove_mode = False
        self.selected = None
        self.app.api.post("/api/premove", {"cancel": True})
        self.app.poll_once()

    def is_promotion(self, frm, to):
        code = self.code_at(frm)
        if not code or code.upper() != "P":
            return False
        rank = int(to[1])
        return (code.isupper() and rank == 8) or (code.islower() and rank == 1)

    def choose_promotion(self, color, callback):
        dlg = tk.Toplevel(self)
        dlg.title("Beförderung")
        dlg.configure(bg=self.app.palette["panel"])
        dlg.transient(self)
        dlg.resizable(False, False)
        UI(self.app).label(dlg, "Figur wählen", bold=True, size=11).pack(padx=12, pady=(10, 6))
        row = UI(self.app).frame(dlg, "panel")
        row.pack(padx=10, pady=(0, 10))
        for ch in "qrbn":
            code = ch.upper() if color == "w" else ch
            img = self.images.get(code)
            b = UI(self.app).button(row, FALLBACK[ch.upper()] if img is None else "",
                                     command=lambda c=ch: (dlg.destroy(), callback(c)),
                                     image=img, width=48, height=48)
            b.pack(side="left", padx=3)
        dlg.grab_set()

    def try_move(self, frm, to):
        st = self.state_data or {}
        pm = self.premove_mode
        promo = "q"
        if self.is_promotion(frm, to) and not self.auto_queen:
            color = st.get("you_color", "w") if pm else st.get("turn", "w")
            self.choose_promotion(color, lambda ch: self.post_move(frm, to, ch, pm))
            return
        self.post_move(frm, to, promo, pm)

    def post_move(self, frm, to, promo, pm):
        payload = {"from": frm, "to": to, "promotion": promo}
        if pm:
            payload["premove"] = True
        res = self.app.api.post("/api/move", payload)
        if "error" in res:
            messagebox.showerror("Zug", res["error"], parent=self)
        else:
            self.app.poll_once()
        self.premove_mode = False

    def toggle_flip(self):
        self.flip = not self.flip
        self.app.api.post("/api/settings", {"flip": self.flip})
        self.draw_board()


class StatsWindow(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.ui = UI(app)
        self.title("Chess · Bot & Rewards")
        self.configure(bg=app.palette["bg"])
        self.resizable(True, True)
        self.vars = {}
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.app.quit)

    def row(self, parent, key, label, col=0, row=0):
        self.ui.label(parent, label, fg="muted", size=8).grid(row=row, column=col * 2,
                                                               sticky="w", padx=(8, 3), pady=1)
        v = tk.StringVar(value="—")
        self.vars[key] = v
        self.ui.label(parent, "", fg="text", size=9, bold=True, textvariable=v).grid(
            row=row, column=col * 2 + 1, sticky="e", padx=(3, 8), pady=1)
        return v

    def build(self):
        outer = self.ui.frame(self, "bg")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        header = self.ui.frame(outer, "bg")
        header.pack(fill="x", pady=(0, 4))
        Mascot(header, self.ui, 34).pack(side="left", padx=(0, 7))
        titles = self.ui.frame(header, "bg")
        titles.pack(side="left")
        self.ui.label(titles, "BOT · REWARDS · ANALYSE", fg="accent", bg="bg", size=12, bold=True).pack(anchor="w")
        self.ui.label(titles, "Live vom lokalen Server", fg="muted", bg="bg", size=9).pack(anchor="w")
        self.ui.label(header, "⋮⋮ ZIEHEN", fg="muted", bg="bg", size=8, bold=True).pack(side="right", padx=(0, 10))
        make_draggable(self, header)

        card = self.ui.card(outer)
        card.pack(fill="x", pady=(0, 6))
        self.ui.label(card, "REWARD", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(6, 1))
        self.reward_bar = self.ui.canvas(card, "panel", height=16)
        self.reward_bar.pack(fill="x", padx=8, pady=(0, 3))
        self.reward_val = self.ui.label(card, "0.00", fg="accent", size=12, bold=True)
        self.reward_val.pack(anchor="e", padx=8, pady=(0, 3))
        self.ui.label(card, "Reward / Zug", fg="muted", size=8).pack(anchor="w", padx=8)
        self.spark_r = self.ui.canvas(card, "panel", height=34)
        self.spark_r.pack(fill="x", padx=8, pady=(1, 3))
        self.ui.label(card, "Reaktionszeit (ms)", fg="muted", size=8).pack(anchor="w", padx=8)
        self.spark_t = self.ui.canvas(card, "panel", height=34)
        self.spark_t.pack(fill="x", padx=8, pady=(1, 5))

        grid = self.ui.card(outer)
        grid.pack(fill="x", pady=(0, 6))
        for col, width in enumerate((88, 120, 88, 120)):
            grid.columnconfigure(col, minsize=width)
        items = [
            ("engine", "Engine"), ("arch", "Arch"), ("device", "Device"), ("ckpt", "Checkpoint"),
            ("planes", "Planes / Aktionen"), ("sims", "MCTS-Sims"), ("cache", "Cache"),
            ("depth", "Tiefe"), ("nodes", "Knoten"), ("best", "Bester Zug"),
            ("eval", "Eval (Weiß)"), ("phase", "Phase"),
            ("rt_last", "Reaktion letzte"), ("rt_avg", "Reaktion Ø"), ("rt_min", "Reaktion min"),
            ("rt_max", "Reaktion max"), ("rw_last", "Reward letzte"), ("rw_avg", "Reward Ø"),
            ("rw_total", "Reward gesamt"), ("wdl", "W / D / L"), ("winrate", "Win-Rate"),
            ("moves", "Züge Bot / Du"), ("games", "Partien"), ("uptime", "Uptime"),
            ("status", "Status"), ("ply", "Ply"), ("premove", "Premove"),
            ("think_delay", "Denkzeit"), ("clocks", "Uhr W / B"),
            ("legal", "Legale Züge"), ("check", "Schach"),
        ]
        for i, (key, lab) in enumerate(items):
            self.row(grid, key, lab, col=i % 2, row=i // 2)

        det = self.ui.card(outer)
        det.pack(fill="both", expand=True)
        self.ui.label(det, "TACTICS · PV · REGLN", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(6, 1))
        self.details = self.ui.text(det, "panel", height=6, wrap="word")
        self.details.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.details.tag_configure("h", foreground=self.app.palette["accent"],
                                   font=("Consolas", 9, "bold"))
        self.details.tag_configure("m", foreground=self.app.palette["muted"])

    def spark(self, canvas, values, color, center_zero=False):
        p = self.app.palette
        canvas.delete("all")
        w = canvas.winfo_width()
        if w < 20:
            w = 300
        h = canvas.winfo_reqheight()
        if h < 10:
            h = 46
        canvas.configure(bg=p["panel"])
        canvas.create_line(0, h / 2, w, h / 2, fill=p["line"])
        if not values:
            canvas.create_text(w / 2, h / 2, text="noch keine Daten", fill=p["muted"],
                               font=("Segoe UI", 8))
            return
        lo, hi = min(values), max(values)
        if center_zero:
            m = max(abs(lo), abs(hi), 0.1)
            lo, hi = -m, m
        elif hi - lo < 1e-6:
            hi = lo + 1
        if len(values) == 1:
            values = [values[0], values[0]]
        pts = []
        for i, v in enumerate(values):
            x = 2 + i * (w - 4) / max(1, len(values) - 1)
            y = h - 3 - (v - lo) / (hi - lo) * (h - 6)
            pts.extend([x, y])
        canvas.create_line(*pts, fill=color, width=2, smooth=True)
        canvas.create_text(4, 4, text=f"{lo:.2f} … {hi:.2f}", anchor="nw",
                           fill=p["muted"], font=("Segoe UI", 7))

    def update_data(self, state, stats, analysis):
        if "error" in stats:
            self.vars["status"].set("Server offline")
            return
        p = self.app.palette
        a = stats.get("analysis", {})
        g = stats.get("game", {})
        rt = stats.get("reaction", {})
        rw = stats.get("reward", {})
        res = stats.get("results", {})
        self.vars["engine"].set(stats.get("engine", "?"))
        self.vars["arch"].set(stats.get("arch", "?"))
        self.vars["device"].set(stats.get("device", "CPU"))
        self.vars["ckpt"].set("ja" if stats.get("checkpoint") else "nein")
        self.vars["planes"].set(f"{stats.get('planes',0)} / {stats.get('actions',0)}")
        self.vars["sims"].set(str(stats.get("sims") or "Baseline"))
        self.vars["cache"].set(str(stats.get("cache", 0)))
        self.vars["depth"].set(str(a.get("depth", 0)))
        self.vars["nodes"].set(str(a.get("nodes", 0)))
        self.vars["best"].set(a.get("best", "—"))
        self.vars["eval"].set(f"{a.get('eval_white',0)/100:+.2f}")
        self.vars["phase"].set(a.get("phase", "—"))
        self.vars["rt_last"].set(f"{rt.get('last',0):.1f} ms")
        self.vars["rt_avg"].set(f"{rt.get('avg',0):.1f} ms")
        self.vars["rt_min"].set(f"{rt.get('min',0):.1f} ms")
        self.vars["rt_max"].set(f"{rt.get('max',0):.1f} ms")
        self.vars["rw_last"].set(f"{rw.get('last',0):+.3f}")
        self.vars["rw_avg"].set(f"{rw.get('avg',0):+.3f}")
        self.vars["rw_total"].set(f"{stats.get('reward_total',0):+.2f}")
        self.vars["wdl"].set(f"{res.get('win',0)} / {res.get('draw',0)} / {res.get('loss',0)}")
        self.vars["winrate"].set(f"{stats.get('win_rate',0)*100:.1f} %")
        mv = stats.get("moves", {})
        self.vars["moves"].set(f"{mv.get('bot_session',0)} / {mv.get('user_session',0)}")
        self.vars["games"].set(str(stats.get("games", 0)))
        self.vars["uptime"].set(f"{stats.get('uptime_s',0):.0f} s")
        self.vars["status"].set(g.get("status", "?"))
        self.vars["ply"].set(str(g.get("ply", 0)))
        self.vars["premove"].set(g.get("premove") or "—")
        self.vars["think_delay"].set(f"{g.get('think_delay',0):.2f} s")
        cl = g.get("clocks", {})
        self.vars["clocks"].set(f"{fmt_time(cl.get('w',0))} / {fmt_time(cl.get('b',0))}")
        self.vars["legal"].set(str(g.get("legal", 0)))
        self.vars["check"].set("ja" if a.get("in_check") else "nein")

        rn = stats.get("reward_norm", 0)
        self.reward_val.configure(text=f"{stats.get('reward_total',0):+.2f}")
        self.reward_bar.delete("all")
        w = self.reward_bar.winfo_width()
        if w < 20:
            w = 300
        self.reward_bar.configure(bg=p["panel"])
        self.reward_bar.create_rectangle(0, 3, w, 15, fill=p["panel2"], outline="")
        half = w / 2
        x = half + rn * half
        self.reward_bar.create_rectangle(min(half, x), 3, max(half, x), 15,
                                         fill=p["accent"], outline="")
        self.reward_bar.create_line(half, 2, half, 16, fill=p["line"])
        self.spark(self.spark_r, stats.get("reward_history", []), p["accent"], True)
        self.spark(self.spark_t, stats.get("reaction_history", []), p["text"], False)

        tactics = stats.get("tactics", {})
        tl = ", ".join(f"{k}×{v}" for k, v in tactics.items()) or "keine"
        pv = " ".join(a.get("pv", [])[:8]) or "—"
        rules = (f"Rochade {g.get('castling','—')} · EP {g.get('ep') or '—'} · "
                 f"50-Züge {g.get('halfmove',0)}/100 · 3-fach {g.get('threefold',False)} · "
                 f"Remis50 {g.get('fifty',False)} · Remisofferte {g.get('draw_offer') or '—'} · "
                 f"Zug {g.get('last_move_ms',0):.0f} ms · "
                 f"Zeit {g.get('time_control',0):.0f}+{g.get('increment',0):.0f}")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", "Taktiken  ", "h")
        self.details.insert("end", tl + "\n")
        self.details.insert("end", "PV        ", "h")
        self.details.insert("end", pv + "\n")
        self.details.insert("end", "Regeln    ", "h")
        self.details.insert("end", rules + "\n", "m")
        self.details.configure(state="disabled")

    def on_theme(self):
        self.configure(bg=self.app.palette["bg"])
        self.details.tag_configure("h", foreground=self.app.palette["accent"])
        self.details.tag_configure("m", foreground=self.app.palette["muted"])


class MatchWindow(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.ui = UI(app)
        self.title("Chess · Match & Settings")
        self.configure(bg=app.palette["bg"])
        self.resizable(False, True)
        self._updating = False
        self._job = None
        self.difficulty = tk.IntVar(value=3)
        self.time_control = tk.IntVar(value=600)
        self.increment = tk.IntVar(value=0)
        self.think_delay = tk.DoubleVar(value=0.6)
        self.bot_enabled = tk.BooleanVar(value=True)
        self.premove = tk.BooleanVar(value=True)
        self.auto_queen = tk.BooleanVar(value=False)
        self.coords = tk.BooleanVar(value=True)
        self.animation = tk.BooleanVar(value=True)
        self.texture = tk.BooleanVar(value=True)
        self.arrows = tk.BooleanVar(value=True)
        self.theme = tk.StringVar(value="duo")
        self.highlight = tk.StringVar(value="yellow")
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.app.quit)
        for v in (self.difficulty, self.time_control, self.increment,
                  self.think_delay, self.bot_enabled, self.premove,
                  self.auto_queen, self.coords, self.animation,
                  self.texture, self.arrows, self.theme, self.highlight):
            v.trace_add("write", lambda *a: self.schedule())

    def build(self):
        outer = self.ui.frame(self, "bg")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        header = self.ui.frame(outer, "bg")
        header.pack(fill="x", pady=(0, 5))
        Mascot(header, self.ui, 34).pack(side="left", padx=(0, 7))
        titles = self.ui.frame(header, "bg")
        titles.pack(side="left")
        self.ui.label(titles, "MATCH · ZEIT · REMIS", fg="accent", bg="bg", size=12, bold=True).pack(anchor="w")
        self.server_lbl = self.ui.label(titles, "Server: lokal", fg="muted", bg="bg", size=9)
        self.server_lbl.pack(anchor="w")
        self.ui.label(header, "⋮⋮ ZIEHEN", fg="muted", bg="bg", size=8, bold=True).pack(side="right", padx=(0, 10))
        make_draggable(self, header)

        s = self.ui.card(outer)
        s.pack(fill="x", pady=(0, 6))
        self.ui.label(s, "EINSTELLUNGEN", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(6, 2))
        def line(parent, label, widget):
            f = self.ui.frame(parent, "panel")
            f.pack(fill="x", padx=8, pady=1)
            self.ui.label(f, label, size=9, width=13, anchor="w").pack(side="left")
            widget(f).pack(side="right", fill="x", expand=True)
        line(s, "Level 1–5", lambda f: self.ui.spin(f, 1, 5, self.difficulty, width=5))
        line(s, "Zeit (s)", lambda f: self.ui.spin(f, 60, 3600, self.time_control, width=7))
        line(s, "Inkrement (s)", lambda f: self.ui.spin(f, 0, 30, self.increment, width=5))
        line(s, "Denkzeit (s)", lambda f: self.ui.spin(f, 0, 5, self.think_delay, width=5))
        line(s, "Theme", lambda f: self.ui.option(f, self.theme, list(PALETTES.keys())))
        line(s, "Highlight", lambda f: self.ui.option(f, self.highlight, ["yellow", "blue", "red"]))
        checks = self.ui.frame(s, "panel")
        checks.pack(fill="x", padx=8, pady=(4, 6))
        checks.columnconfigure(0, minsize=110)
        checks.columnconfigure(1, minsize=110)
        opts = [("Bot", self.bot_enabled), ("Premove", self.premove),
                ("Auto-Dame", self.auto_queen), ("Koordinaten", self.coords),
                ("Animation", self.animation), ("Storybook", self.texture),
                ("Pfeile", self.arrows)]
        for i, (text, var) in enumerate(opts):
            self.ui.check(checks, text, var).grid(row=i // 2, column=i % 2,
                                                   sticky="w", pady=1)

        b = self.ui.card(outer)
        b.pack(fill="x", pady=(0, 6))
        self.ui.label(b, "PARTIE", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(6, 2))
        self.ui.button(b, "Neue Partie", self.new_game, accent=True,
                       tooltip="Neue Partie · N").pack(fill="x", padx=8, pady=1)
        row1 = self.ui.frame(b, "panel"); row1.pack(fill="x", padx=8, pady=1)
        self.ui.button(row1, "Zurück", lambda: self.post("/api/undo"),
                       tooltip="Letzten Zug zurück · U").pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.ui.button(row1, "Tipp", self.hint,
                       tooltip="Bester Zug · H").pack(side="left", expand=True, fill="x", padx=(3, 0))
        row2 = self.ui.frame(b, "panel"); row2.pack(fill="x", padx=8, pady=1)
        self.ui.button(row2, "Drehen", self.flip,
                       tooltip="Brett drehen · F").pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.ui.button(row2, "Aufgabe", self.resign,
                       tooltip="Partie aufgeben").pack(side="left", expand=True, fill="x", padx=(3, 0))
        row3 = self.ui.frame(b, "panel"); row3.pack(fill="x", padx=8, pady=1)
        self.ui.button(row3, "Remis Anspruch", lambda: self.post("/api/claim_draw"),
                       tooltip="50-Züge / 3-fach / Material").pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.ui.button(row3, "Remis Einig", lambda: self.post("/api/agree_draw"),
                       tooltip="Remis sofort vereinbaren").pack(side="left", expand=True, fill="x", padx=(3, 0))
        row4 = self.ui.frame(b, "panel"); row4.pack(fill="x", padx=8, pady=1)
        self.ui.button(row4, "Remis anbieten", self.offer_draw,
                       tooltip="Bot entscheidet · O").pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.ui.button(row4, "Abbruch", self.abort,
                       tooltip="Nur vor Zug 2 · A").pack(side="left", expand=True, fill="x", padx=(3, 0))
        self.ui.button(b, "Markierungen löschen", self.clear_marks,
                       tooltip="Rechtsklick-Markierungen/Pfeile · C").pack(fill="x", padx=8, pady=(1, 6))

        info = self.ui.card(outer)
        info.pack(fill="both", expand=True)
        self.ui.label(info, "LIVE", fg="muted", size=9, bold=True).pack(anchor="w", padx=8, pady=(8, 4))
        self.info = self.ui.text(info, "panel", height=12, wrap="word")
        self.info.configure(font=("Consolas", 8))
        self.info.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.info.tag_configure("h", foreground=self.app.palette["accent"],
                                font=("Consolas", 9, "bold"))

    def settings_payload(self):
        return {
            "difficulty": int(self.difficulty.get()),
            "time_control": int(self.time_control.get()),
            "increment": int(self.increment.get()),
            "think_delay": float(self.think_delay.get()),
            "bot_enabled": bool(self.bot_enabled.get()),
            "premove": bool(self.premove.get()),
            "auto_queen": bool(self.auto_queen.get()),
            "coords": bool(self.coords.get()),
            "animation": bool(self.animation.get()),
            "texture": bool(self.texture.get()),
            "arrows": bool(self.arrows.get()),
            "theme": self.theme.get(),
            "highlight": self.highlight.get(),
        }

    def schedule(self):
        if self._updating:
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(300, self.flush)

    def flush(self):
        self._job = None
        payload = self.settings_payload()
        self.app.api.post("/api/settings", payload)
        if payload["theme"] in PALETTES and payload["theme"] != self.app.theme_name:
            self.app.set_theme(payload["theme"])
        self.app.poll_once()

    def post(self, path, payload=None):
        res = self.app.api.post(path, payload or {})
        if "error" in res:
            messagebox.showerror("Match", res["error"], parent=self)
        self.app.poll_once()

    def new_game(self):
        settings = self.settings_payload()
        d = dict(settings)
        d.update({"you_color": "w", "settings": settings})
        self.post("/api/new", d)

    def hint(self):
        res = self.app.api.post("/api/hint", {})
        if "san" in res:
            messagebox.showinfo("Tipp", res["san"], parent=self)
        elif "error" in res:
            messagebox.showerror("Tipp", res["error"], parent=self)

    def flip(self):
        cur = bool((self.app.last_state or {}).get("settings", {}).get("flip", False))
        self.post("/api/settings", {"flip": not cur})

    def resign(self):
        if messagebox.askyesno("Aufgabe", "Wirklich aufgeben?", parent=self):
            self.post("/api/resign", {})

    def offer_draw(self):
        self.post("/api/offer_draw", {})

    def abort(self):
        self.post("/api/abort", {})

    def clear_marks(self):
        self.app.root.clear_marks()
        self.app.poll_once()

    def update_data(self, state, stats, analysis):
        if "error" in state:
            self.server_lbl.configure(text="Server: offline")
            return
        self.server_lbl.configure(text=f"Server: {API}")
        st = state.get("settings", {})
        self._updating = True
        self.difficulty.set(int(state.get("difficulty", 3)))
        self.time_control.set(int(state.get("time_control", 600)))
        self.increment.set(int(state.get("increment", 0)))
        self.think_delay.set(float(state.get("think_delay", 0.6)))
        self.bot_enabled.set(bool(state.get("bot_enabled", True)))
        for key, var in [("premove", self.premove), ("auto_queen", self.auto_queen),
                         ("coords", self.coords), ("animation", self.animation),
                         ("texture", self.texture), ("arrows", self.arrows)]:
            var.set(bool(st.get(key, var.get())))
        if st.get("theme") in PALETTES:
            self.theme.set(st["theme"])
        if st.get("highlight") in ("yellow", "blue", "red"):
            self.highlight.set(st["highlight"])
        self._updating = False
        r = state.get("rules", {})
        clocks = state.get("clocks", {})
        txt = (f"Status      {state.get('status','?')}\n"
               f"Am Zug      {'Weiß' if state.get('turn')=='w' else 'Schwarz'}\n"
               f"Uhren       W {fmt_time(clocks.get('w',0))} · B {fmt_time(clocks.get('b',0))}\n"
               f"Zeit        {state.get('time_control',0):.0f} + {state.get('increment',0):.0f}s\n"
               f"Premove     {state.get('premove') or '—'} · Remis {state.get('draw_offer') or '—'}\n"
               f"Zug         {state.get('last_move_ms',0):.0f} ms · {r.get('legal_count',0)} legal\n"
               f"Regeln      {r.get('castling','—')} · EP {r.get('ep_square') or '—'} · 50 {r.get('halfmove_clock',0)}/100\n"
               f"Draws       3-fach {r.get('can_claim_threefold',False)} · 50 {r.get('can_claim_fifty',False)}\n"
               f"Material    {r.get('material_balance',0):+.1f} · {r.get('phase','—')}\n"
               f"Shortcuts   N/U/H/F/O/A/C/Esc")
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", txt)
        self.info.configure(state="disabled")

    def on_theme(self):
        self.configure(bg=self.app.palette["bg"])
        self.info.tag_configure("h", foreground=self.app.palette["accent"])


class App:
    def __init__(self):
        self.api = Api(API)
        initial = self.api.get("/api/state")
        name = (initial.get("settings", {}).get("theme", "duo")
                if isinstance(initial, dict) else "duo")
        self.theme_name = name if name in PALETTES else "duo"
        self.palette = dict(PALETTES[self.theme_name])
        self.last_state = initial if isinstance(initial, dict) and "error" not in initial else None
        self.last_stats = None
        self.last_analysis = None
        self.low = os.environ.get("CHESS_LOW_RAM") == "1"
        self.font = "Segoe UI" if os.name == "nt" else "DejaVu Sans"
        self.root = GameWindow(self)
        self.stats = StatsWindow(self.root, self)
        self.match = MatchWindow(self.root, self)
        self.windows = [self.root, self.stats, self.match]
        self.place_windows()
        self.bind_keys()
        self.root.after(200, self.poll)

    def bind_keys(self):
        for w in self.windows:
            w.bind("<Key>", self.on_key, add="+")

    def on_key(self, event):
        if event.widget.winfo_class() in ("Entry", "Spinbox", "Text", "TEntry", "TSpinbox"):
            return
        k = event.keysym.lower()
        if k == "n":
            self.match.new_game()
        elif k == "u":
            self.match.post("/api/undo")
        elif k == "h":
            self.match.hint()
        elif k == "f":
            self.match.flip()
        elif k == "o":
            self.match.offer_draw()
        elif k == "a":
            self.match.abort()
        elif k == "c":
            self.match.clear_marks()
        elif k == "escape":
            self.root.cancel_premove()

    def place_windows(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        h = min(840, max(600, sh - 60))
        sizes = [(820, h), (460, h), (340, h)]
        total = sum(w for w, _ in sizes) + 20 * (len(sizes) + 1)
        if sw >= total:
            y = max(10, min(30, (sh - h) // 2))
            x = 20
            for win, (w, hh) in zip(self.windows, sizes):
                win.geometry(f"{w}x{hh}+{x}+{y}")
                x += w + 20
        else:
            # Kleine Laptops: gekachelt, aber immer innerhalb des Bildschirms + ziehbar.
            for i, (win, (w, hh)) in enumerate(zip(self.windows, sizes)):
                x = max(10, min(20 + i * 35, max(10, sw - w - 10)))
                y = max(10, min(20 + i * 30, max(10, sh - hh - 10)))
                win.geometry(f"{w}x{hh}+{x}+{y}")

    def set_theme(self, name):
        if name not in PALETTES:
            return
        self.theme_name = name
        self.palette = dict(PALETTES[name])
        for w in self.windows:
            UI(self).apply(w)
            if hasattr(w, "on_theme"):
                w.on_theme()

    def poll_once(self):
        state = self.api.get("/api/state")
        stats = self.api.get("/api/stats")
        analysis = {} if self.low else self.api.get("/api/analysis")
        self.last_state, self.last_stats, self.last_analysis = state, stats, analysis
        if "error" not in state:
            remote_theme = state.get("settings", {}).get("theme")
            if remote_theme in PALETTES and remote_theme != self.theme_name:
                self.set_theme(remote_theme)
        for w in self.windows:
            try:
                w.update_data(state, stats, analysis)
            except Exception as e:
                print("UI update:", e)
        return state

    def poll(self):
        self.poll_once()
        self.root.after(1200 if self.low else 600, self.poll)

    def quit(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    global PORT, API
    ap = argparse.ArgumentParser(description="Chess Bot v6 · 3 native Fenster")
    ap.add_argument("--low", action="store_true",
                    help="2-GB-RAM-Modus: kleinere MCTS, keine Dauer-Analyse, langsameres Polling")
    ap.add_argument("--port", type=int, default=None, help="Port für Server + UI")
    args, _ = ap.parse_known_args()
    if args.low:
        os.environ["CHESS_LOW_RAM"] = "1"
    if args.port:
        os.environ["CHESS_PORT"] = str(args.port)
        os.environ["PORT"] = str(args.port)
    PORT = int(os.environ.get("CHESS_PORT", "8000"))
    API = f"http://127.0.0.1:{PORT}"
    if args.low:
        print("LOW-RAM: MCTS kleiner, Analyse aus, Poll 1200 ms")
    if not ensure_server():
        print("Warnung: Server nicht erreichbar – Fenster starten trotzdem.")
    app = App()
    app.run()


if __name__ == "__main__":
    main()
