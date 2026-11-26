"""One-command browser startup and Windows UTF-16 dotenv regression tests."""
from __future__ import annotations

import importlib.util
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import main as launcher


class LauncherTests(unittest.TestCase):
    def test_uses_local_venv_even_when_invoked_from_global_python(self):
        pretend_python = Path(__file__).resolve()  # an existing file; no child is run
        with patch.object(launcher, "_local_python", return_value=pretend_python), \
             patch.object(sys, "prefix", "/not-the-project-venv"), \
             patch.object(sys, "argv", [str(launcher.ROOT / "main.py")]), \
             patch.object(launcher.subprocess, "call", return_value=17) as call:
            self.assertEqual(launcher.main(), 17)
        call.assert_called_once_with(
            [str(pretend_python), str(launcher.ROOT / "main.py")], cwd=launcher.ROOT)

    def test_opens_default_browser_only_after_binding_an_available_server(self):
        from werkzeug.serving import make_server

        servers = []
        opened = queue.Queue()
        errors = []

        def capture_server(*args, **kwargs):
            server = make_server(*args, **kwargs)
            servers.append(server)
            return server

        def capture_url(url, new=0):
            opened.put(url)
            return True

        def run():
            try:
                launcher.serve()
            except BaseException as exc:
                errors.append(exc)

        with patch.dict(os.environ, {"PORT": "0", "CHESS_NO_BROWSER": "0"}), \
             patch("werkzeug.serving.make_server", side_effect=capture_server), \
             patch("webbrowser.open", side_effect=capture_url) as browser:
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            try:
                url = opened.get(timeout=12)
                self.assertTrue(url.startswith("http://127.0.0.1:"), url)
                with urllib.request.urlopen(url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"Chess Garden", response.read())
                browser.assert_called_once_with(url, new=2)
            finally:
                for server in servers:
                    server.shutdown()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)

    @unittest.skipUnless(importlib.util.find_spec("dotenv"),
                         "install test-only python-dotenv to exercise Flask's parser")
    def test_server_ignores_utf16_dotenv_from_windows_powershell(self):
        # Flask 3 + python-dotenv auto-read this as UTF-8 in app.run unless
        # load_dotenv=False is specified. Never edit or delete the user's .env.
        with tempfile.TemporaryDirectory() as work:
            Path(work, ".env").write_bytes(b"\xff\xfe" +
                                           "CHESS_LOW_RAM=1\n".encode("utf-16-le"))
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            env = dict(os.environ, CHESS_HOST="127.0.0.1", PORT=str(port))
            env.pop("FLASK_SKIP_DOTENV", None)
            proc = subprocess.Popen([sys.executable, str(launcher.ROOT / "server.py")],
                                    cwd=work, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            try:
                url = f"http://127.0.0.1:{port}/api/state"
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        break
                    try:
                        with urllib.request.urlopen(url, timeout=.3) as response:
                            self.assertEqual(response.status, 200)
                            return
                    except (OSError, urllib.error.URLError):
                        time.sleep(.05)
                self.fail(f"Server did not start with a UTF-16 .env; exit={proc.poll()}")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    output, _ = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    output, _ = proc.communicate(timeout=5)
                if proc.returncode not in (0, -15) and "UnicodeDecodeError" in output:
                    self.fail(output)


if __name__ == "__main__":
    unittest.main()
