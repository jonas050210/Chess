#!/usr/bin/env python3
"""Start the local Chess Garden website and open it in the default browser.

This launcher uses the repository's .venv when present, even if invoked with
"py main.py" or "python3 main.py" from a different Python installation.
Training remains a separate, terminal-only command.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def _local_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _open_browser(url: str) -> None:
    try:
        if not webbrowser.open(url, new=2):
            print(f"Browser konnte nicht automatisch geöffnet werden: {url}", flush=True)
    except Exception as exc:
        # A missing GUI/browser must never bring down the local chess server.
        print(f"Browser konnte nicht automatisch geöffnet werden ({exc}): {url}",
              file=sys.stderr, flush=True)


def serve() -> int:
    """Bind first; only open a browser if the server can actually accept it."""
    from werkzeug.serving import make_server
    from server import HOST, LOW_RAM, app

    port = int(os.environ.get("PORT", "8000"))
    with make_server(HOST, port, app, threaded=True) as httpd:
        # 0.0.0.0 is a bind address, never a browser destination.
        browser_host = ("127.0.0.1" if HOST in {"0.0.0.0", ""} else
                        "[::1]" if HOST == "::" else
                        f"[{HOST}]" if ":" in HOST and not HOST.startswith("[") else HOST)
        url = f"http://{browser_host}:{httpd.server_port}/"
        print(f"Chess Garden: {url} · Low-RAM={LOW_RAM} · Beenden mit Strg+C",
              flush=True)
        if os.environ.get("CHESS_NO_BROWSER") != "1":
            threading.Thread(target=_open_browser, args=(url,), daemon=True,
                             name="open-chess-browser").start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nChess Garden beendet.", flush=True)
    return 0


def main() -> int:
    local_python = _local_python()
    if local_python.is_file() and Path(sys.prefix).resolve() != VENV.resolve():
        # The launcher itself needs only the standard library. Delegate to the
        # installed venv BEFORE importing Flask, chess or NumPy.
        try:
            return subprocess.call([str(local_python), str(ROOT / "main.py"),
                                    *sys.argv[1:]], cwd=ROOT)
        except KeyboardInterrupt:
            # Ctrl+C also reaches the child console process on Windows.
            return 130
        except OSError as exc:
            print(f"Lokale Python-Umgebung konnte nicht gestartet werden: {exc}",
                  file=sys.stderr)
            return 1
    os.chdir(ROOT)
    try:
        return serve()
    except ModuleNotFoundError as exc:
        if exc.name not in {"flask", "werkzeug", "chess", "numpy"}:
            raise
        print("Abhängigkeiten fehlen. Einmalig windows\\setup.bat (Windows) "
              "oder python3 -m venv .venv && .venv/bin/python -m pip install "
              "-r requirements.txt (Linux) ausführen.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
