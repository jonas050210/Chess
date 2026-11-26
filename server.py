"""Lokaler Chess-Server v6.2: Storybook-UI, ZIP-Pieces, Drag/Animation, 3 Fenster, Live-Analyse."""
from __future__ import annotations

import math
import os
import threading
import time
from urllib.parse import urlsplit

import chess
from chess.polyglot import zobrist_hash
from flask import Flask, jsonify, request, send_from_directory

from ai import ACTION_SIZE, HIDDEN, PLANES, HAS_TORCH, board_meta
from ai.analysis import AnalysisEngine
from ai.baseline import BaselineBot
from ai.bot import AIBot, SIMS
from ai.stats import stats
import ai.bot as bot_mod

LOW_RAM = os.environ.get("CHESS_LOW_RAM") == "1"
# Loopback is the safe default: this API has no authentication. Set CHESS_HOST=0.0.0.0
# only when LAN access is intentional and the host is protected by a firewall.
HOST = os.environ.get("CHESS_HOST", "127.0.0.1")
if LOW_RAM:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    SIMS.update({1: 4, 2: 8, 3: 12, 4: 16, 5: 24})
    bot_mod.CACHE_LIMIT = 2000

if HAS_TORCH:
    import torch
    torch.set_num_threads(1 if LOW_RAM else min(4, os.cpu_count() or 4))

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
NP_CKPT = os.path.join(ROOT, "checkpoints", "model.npz")
TORCH_CKPT = os.path.join(ROOT, "checkpoints", "model_torch.pt")

app = Flask(__name__, static_folder=None)
app.config["JSON_SORT_KEYS"] = False


@app.before_request
def protect_local_api():
    # The browser UI and Tk client use JSON. Reject simple form posts and cross-origin
    # browser requests to reduce localhost CSRF/DNS-rebinding exposure.
    if request.method != "POST":
        return None
    if request.mimetype != "application/json":
        return jsonify({"error": "Content-Type must be application/json"}), 415
    if HOST in ("127.0.0.1", "localhost", "::1"):
        host = urlsplit(f"//{request.host}").hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return jsonify({"error": "Invalid Host"}), 400
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        return jsonify({"error": "Cross-origin request rejected"}), 403
    return None


bot = AIBot(checkpoint=NP_CKPT, torch_checkpoint=TORCH_CKPT if HAS_TORCH else None)
fallback = BaselineBot()

INIT_COUNT = {
    "P": 8, "N": 2, "B": 2, "R": 2, "Q": 1, "K": 1,
    "p": 8, "n": 2, "b": 2, "r": 2, "q": 1, "k": 1,
}
ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4, "K": 5}
PROMO_MAP = {"q": chess.QUEEN, "r": chess.ROOK,
             "b": chess.BISHOP, "n": chess.KNIGHT, "": chess.QUEEN}
PROMO_CHAR = {chess.QUEEN: "q", chess.ROOK: "r",
              chess.BISHOP: "b", chess.KNIGHT: "n"}


def captured_material(board: chess.Board) -> dict:
    cnt = {k: 0 for k in INIT_COUNT}
    for p in board.piece_map().values():
        cnt[p.symbol()] += 1
    out = {"w": [], "b": []}
    for sym, init in INIT_COUNT.items():
        diff = init - cnt[sym]
        if diff <= 0:
            continue
        if sym.islower():
            out["w"].extend([sym] * diff)
        else:
            out["b"].extend([sym] * diff)
    for k in out:
        out[k].sort(key=lambda s: ORDER.get(s.upper(), 9))
    return out


def pgn_from_san(san: list[str]) -> str:
    parts = []
    for i in range(0, len(san), 2):
        parts.append(f"{i//2+1}. {san[i]}" + (f" {san[i+1]}" if i + 1 < len(san) else ""))
    return " ".join(parts)


class Session:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = {
            "theme": "duo", "highlight": "yellow", "coords": True,
            "animation": True, "auto_queen": False, "premove": True,
            "texture": True, "arrows": True, "flip": False,
        }
        self.new("w", 3, 600, True, 0.6, 0)

    def _finished(self) -> bool:
        return (self.result_override is not None or self.timed_out is not None
                or self.board.outcome(claim_draw=True) is not None)

    def _tick(self):
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        if self.clock_started and not self._finished():
            key = "w" if self.board.turn == chess.WHITE else "b"
            self.clocks[key] = max(0.0, self.clocks[key] - dt)
            if self.clocks[key] <= 0:
                self.timed_out = {"status": "timeout",
                                  "winner": "b" if key == "w" else "w"}
                self.bot_pending = False
                self.premove = None

    def _apply(self, move: chess.Move) -> bool:
        self._tick()
        if self._finished():
            return False
        mover = "w" if self.board.turn == chess.WHITE else "b"
        san = self.board.san(move)
        elapsed = time.time() - self.last_move_started_at if self.clock_started else 0.0
        self.board.push(move)
        self.clocks[mover] = max(0.0, self.clocks[mover] + self.increment)
        self.move_history.append(move)
        self.san_history.append(san)
        self.last_move = move
        self.last_move_ms = max(0.0, elapsed * 1000.0)
        self.move_times.append(round(self.last_move_ms, 1))
        self.started = True
        self.last_tick = time.time()
        self.last_move_started_at = time.time()
        return True

    def _find_move(self, frm: str, to: str, promo_char: str = "q"):
        try:
            f, t = chess.parse_square(frm), chess.parse_square(to)
        except Exception:
            return None
        pp = PROMO_MAP.get(str(promo_char or "q").lower(), chess.QUEEN)
        for m in self.board.legal_moves:
            if m.from_square == f and m.to_square == t:
                if m.promotion:
                    if m.promotion == pp:
                        return m
                else:
                    return m
        return None

    def set_premove(self, frm: str, to: str, promo_char: str = "q") -> bool:
        try:
            f = chess.parse_square(frm)
        except Exception:
            return False
        piece = self.board.piece_at(f)
        if piece is None or piece.color != self.you:
            return False
        self.premove = {"from": frm, "to": to, "promotion": promo_char or "q"}
        return True

    def premove_uci(self):
        if not self.premove:
            return None
        u = self.premove["from"] + self.premove["to"]
        if self.premove.get("promotion", "q") != "q":
            u += self.premove["promotion"]
        return u

    def _bot_move(self):
        if self._finished():
            return None
        before = board_meta(self.board)["material_balance"]
        t0 = time.perf_counter()
        t_wall = time.time()
        mv = bot.choose_move(self.board.copy(stack=True), self.difficulty)
        dt = time.perf_counter() - t0
        started_at = getattr(self, "bot_requested_at", None) or t_wall
        reaction = max(dt, time.time() - started_at)
        if mv is None or not self.board.is_legal(mv):
            mv = fallback.choose_move(self.board, 2)
        if mv is None or not self.board.is_legal(mv):
            legal = list(self.board.legal_moves)
            mv = legal[0] if legal else None
        if mv is None:
            return None
        uci = mv.uci()
        if not self._apply(mv):
            return None
        after = board_meta(self.board)["material_balance"]
        persp = 1.0 if self.bot_color == chess.WHITE else -1.0
        reward = math.tanh(((after - before) * persp) / 5.0) - min(dt, 2.0) * 0.01
        stats.record_bot_move(reaction, reward, uci)
        return uci

    def _bot_async(self):
        if self.think_delay > 0:
            time.sleep(self.think_delay)
        with self.lock:
            if (not self.bot_pending or not self.bot_enabled or self._finished()
                    or self.board.turn != self.bot_color):
                self.bot_pending = False
                return
            self.last_bot_move = self._bot_move()
            self.bot_pending = False
            # Premove nach dem Bot-Zug ausführen, falls noch legal.
            if self.premove and self.settings.get("premove", True) and not self._finished():
                pm = self.premove
                self.premove = None
                mv = self._find_move(pm["from"], pm["to"], pm.get("promotion", "q"))
                if mv is not None and self.board.is_legal(mv) and self._apply(mv):
                    stats.record_user_move()
            self._schedule_bot()

    def _schedule_bot(self) -> bool:
        if (self.bot_enabled and not self._finished()
                and self.board.turn == self.bot_color and not self.bot_pending):
            self.bot_pending = True
            self.bot_requested_at = time.time()
            threading.Thread(target=self._bot_async, daemon=True).start()
            return True
        return False

    def apply_settings(self, d: dict):
        with self.lock:
            for k in ("theme", "highlight", "coords", "animation",
                      "auto_queen", "premove", "texture", "arrows", "flip"):
                if k in d:
                    v = d[k]
                    if k in ("coords", "animation", "auto_queen", "premove",
                             "texture", "arrows", "flip"):
                        v = bool(v)
                    self.settings[k] = v
            if "difficulty" in d:
                self.difficulty = max(1, min(5, int(d["difficulty"])))
            if "bot_enabled" in d:
                self.bot_enabled = bool(d["bot_enabled"])
            if "think_delay" in d:
                self.think_delay = max(0.0, min(5.0, float(d["think_delay"])))
            if "time_control" in d:
                self.time_control = max(30.0, float(d["time_control"]))
                if not self.started:
                    self.clocks = {"w": self.time_control, "b": self.time_control}
            if "increment" in d:
                self.increment = max(0.0, min(30.0, float(d["increment"])))
            self._schedule_bot()

    def new(self, you_color="w", difficulty=3, time_control=600,
            bot_enabled=True, think_delay=0.6, increment=0, settings=None):
        with self.lock:
            self.board = chess.Board()
            self.you_color = you_color if you_color in ("w", "b") else "w"
            self.you = chess.WHITE if self.you_color == "w" else chess.BLACK
            self.bot_color = not self.you
            self.difficulty = max(1, min(5, int(difficulty)))
            self.time_control = max(30.0, float(time_control))
            self.increment = max(0.0, min(30.0, float(increment)))
            self.think_delay = max(0.0, min(5.0, float(think_delay)))
            self.clocks = {"w": self.time_control, "b": self.time_control}
            self.last_move = None
            self.move_history: list[chess.Move] = []
            self.san_history: list[str] = []
            self.started = False
            self.clock_started = True
            self.last_tick = time.time()
            self.bot_enabled = bool(bot_enabled)
            self.bot_pending = False
            self.bot_requested_at = None
            self.last_bot_move = None
            self.result_override = None
            self.timed_out = None
            self.result_recorded = False
            self.premove = None
            self.draw_offered_by = None
            self.last_draw_offer = None
            self.move_times = []
            self.last_move_ms = 0.0
            self.last_move_started_at = time.time()
            if settings:
                self.apply_settings(settings)
            bot.reset()
            stats.new_game()
            self._schedule_bot()
            return self.state()

    def state(self, extra: dict | None = None) -> dict:
        with self.lock:
            self._tick()
            if self._finished():
                self.bot_pending = False
            outcome = self.board.outcome(claim_draw=True)
            status, winner = "playing", None
            if self.result_override is not None:
                status = self.result_override["status"]
                winner = self.result_override["winner"]
            elif self.timed_out is not None:
                status = self.timed_out["status"]
                winner = self.timed_out["winner"]
            elif outcome is not None:
                status = outcome.termination.name.lower()
                winner = ("w" if outcome.winner == chess.WHITE else
                          "b" if outcome.winner == chess.BLACK else None)
            elif self.board.is_check():
                status = "check"
            if self._finished() and not self.result_recorded:
                bot_str = "w" if self.bot_color == chess.WHITE else "b"
                stats.record_result(status, winner, bot_str)
                self.result_recorded = True

            king_sq = self.board.king(self.board.turn) if self.board.is_check() else None
            data = {
                "fen": self.board.fen(),
                "turn": "w" if self.board.turn == chess.WHITE else "b",
                "legal": [m.uci() for m in self.board.legal_moves],
                "last_move": self.last_move.uci() if self.last_move else None,
                "san": list(self.san_history),
                "pgn": pgn_from_san(self.san_history),
                "status": status,
                "winner": winner,
                "check": self.board.is_check(),
                "check_square": chess.square_name(king_sq) if king_sq is not None else None,
                "captured": captured_material(self.board),
                "clocks": {k: round(v, 2) for k, v in self.clocks.items()},
                "you_color": self.you_color,
                "bot_color": "w" if self.bot_color == chess.WHITE else "b",
                "difficulty": self.difficulty,
                "bot_enabled": self.bot_enabled,
                "bot_thinking": self.bot_pending,
                "last_bot_move": self.last_bot_move,
                "think_delay": self.think_delay,
                "started": self.started,
                "clock_started": self.clock_started,
                "time_control": self.time_control,
                "increment": self.increment,
                "premove": self.premove_uci(),
                "draw_offer": self.last_draw_offer,
                "last_move_ms": round(self.last_move_ms, 1),
                "move_times": list(self.move_times[-20:]),
                "settings": dict(self.settings),
                "rules": board_meta(self.board),
                "ai": {
                    "engine": bot.engine,
                    "checkpoint": bot.has_checkpoint,
                    "device": bot.device,
                    "torch": HAS_TORCH,
                    "planes": PLANES,
                    "action_size": ACTION_SIZE,
                    "hidden": HIDDEN,
                    "arch": "ResNet" if bot.engine == "torch-mcts" else f"MLP {HIDDEN}",
                    "cache_size": bot.cache_size,
                    "simulations": SIMS.get(self.difficulty, 40) if bot.has_checkpoint else None,
                },
            }
            if extra:
                data.update(extra)
            return data


session = Session()
analysis_engine = AnalysisEngine()
analysis_lock = threading.Lock()
analysis_state = {"key": None, "fen": None, "result": None,
                  "depth": 0, "thinking": True, "updated": 0.0}


def analysis_loop():
    while True:
        with session.lock:
            board = session.board.copy(stack=True)
            key = zobrist_hash(board)
            finished = session._finished()
        if finished:
            with analysis_lock:
                analysis_state["thinking"] = False
            time.sleep(0.5)
            continue
        with analysis_lock:
            stale = analysis_state.get("key") != key
        if stale:
            analysis_engine.bot.clear()
        for depth in (2, 3):
            with session.lock:
                if zobrist_hash(session.board) != key or session._finished():
                    break
            res = analysis_engine.analyze(board, max_depth=depth)
            with analysis_lock:
                analysis_state.update({
                    "key": key, "fen": board.fen(), "result": res,
                    "depth": depth, "thinking": depth < 3,
                    "updated": time.time(),
                })
            stats.record_analysis(key, res)
            time.sleep(0.18)
        time.sleep(0.45)


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.route("/static/<path:p>")
def static_files(p):
    return send_from_directory(WEB, p)


@app.route("/api/state")
def api_state():
    return jsonify(session.state())


@app.route("/api/analysis")
def api_analysis():
    with session.lock:
        key = zobrist_hash(session.board)
        fen = session.board.fen()
        finished = session._finished()
    with analysis_lock:
        snap = dict(analysis_state)
    fresh = snap.get("key") == key
    return jsonify({
        "finished": finished,
        "fen": fen,
        "thinking": (not finished) and (not LOW_RAM) and
                    (snap.get("thinking", True) or not fresh),
        "depth": snap.get("depth", 0) if fresh else 0,
        "updated": snap.get("updated", 0.0),
        "result": snap.get("result") if fresh else None,
    })


@app.route("/api/stats")
def api_stats():
    st = session.state()
    with session.lock:
        key = zobrist_hash(session.board)
    with analysis_lock:
        snap = dict(analysis_state)
    res = snap.get("result") if snap.get("key") == key else None
    return jsonify(stats.snapshot(st, res))


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        d = request.get_json(force=True, silent=True) or {}
        session.apply_settings(d)
    return jsonify(session.state())


@app.route("/api/new", methods=["POST"])
def api_new():
    d = request.get_json(force=True, silent=True) or {}
    return jsonify(session.new(
        d.get("you_color", "w"), d.get("difficulty", 3),
        d.get("time_control", 600), d.get("bot_enabled", True),
        d.get("think_delay", 0.6), d.get("increment", 0),
        d.get("settings"),
    ))


@app.route("/api/config", methods=["POST"])
def api_config():
    d = request.get_json(force=True, silent=True) or {}
    session.apply_settings(d)
    return jsonify(session.state())


@app.route("/api/move", methods=["POST"])
def api_move():
    d = request.get_json(force=True, silent=True) or {}
    frm, to = d.get("from", ""), d.get("to", "")
    promo_char = str(d.get("promotion", "q") or "q").lower()
    with session.lock:
        session._tick()
        if session._finished():
            return jsonify({"error": "Partie beendet"}), 400
        if session.bot_enabled and session.board.turn != session.you:
            if d.get("premove") and session.bot_pending and session.settings.get("premove", True):
                if session.set_premove(frm, to, promo_char):
                    return jsonify(session.state({"premove_set": session.premove_uci()}))
            return jsonify({"error": "nicht dein Zug"}), 400
        move = session._find_move(frm, to, promo_char)
        if move is None:
            return jsonify({"error": "illegaler Zug"}), 400
        if not session._apply(move):
            return jsonify({"error": "Zeit abgelaufen"}), 400
        stats.record_user_move()
        session._schedule_bot()
    return jsonify(session.state({"your_move": move.uci()}))


@app.route("/api/premove", methods=["POST"])
def api_premove():
    d = request.get_json(force=True, silent=True) or {}
    with session.lock:
        if d.get("cancel"):
            session.premove = None
        else:
            if not session.settings.get("premove", True):
                return jsonify({"error": "Premove ist aus"}), 400
            if not session.set_premove(d.get("from", ""), d.get("to", ""),
                                       str(d.get("promotion", "q") or "q")):
                return jsonify({"error": "ungültiger Premove"}), 400
    return jsonify(session.state())


@app.route("/api/hint", methods=["POST"])
def api_hint():
    with session.lock:
        if session._finished():
            return jsonify({"error": "Partie beendet"}), 400
        mv = bot.hint(session.board.copy(stack=True), session.difficulty)
        if mv is None or not session.board.is_legal(mv):
            return jsonify({"error": "kein Zug"}), 400
        return jsonify({"uci": mv.uci(), "san": session.board.san(mv)})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    with session.lock:
        n = 2 if session.bot_enabled and len(session.move_history) >= 2 else 1
        for _ in range(min(n, len(session.move_history))):
            session.board.pop()
            session.move_history.pop()
            session.san_history.pop()
            if session.move_times:
                session.move_times.pop()
        session.last_move = session.move_history[-1] if session.move_history else None
        session.last_move_ms = session.move_times[-1] if session.move_times else 0.0
        session.last_tick = time.time()
        session.last_move_started_at = time.time()
        session.result_override = None
        session.timed_out = None
        session.result_recorded = False
        session.bot_pending = False
        session.last_bot_move = None
        session.premove = None
        session.draw_offered_by = None
        session.last_draw_offer = None
        bot.reset()
    return jsonify(session.state())


@app.route("/api/resign", methods=["POST"])
def api_resign():
    d = request.get_json(force=True, silent=True) or {}
    color = d.get("color", session.you_color)
    if color not in ("w", "b"):
        color = session.you_color
    with session.lock:
        session.result_override = {"status": "resignation",
                                   "winner": "b" if color == "w" else "w"}
        session.bot_pending = False
        session.premove = None
    return jsonify(session.state())


@app.route("/api/claim_draw", methods=["POST"])
def api_claim_draw():
    with session.lock:
        b = session.board
        if (b.can_claim_threefold_repetition() or b.can_claim_fifty_moves()
                or b.is_insufficient_material()):
            session.result_override = {"status": "claimed_draw", "winner": None}
            session.bot_pending = False
            session.premove = None
        else:
            return jsonify({"error": "kein Remis-Anspruch"}), 400
    return jsonify(session.state())


@app.route("/api/agree_draw", methods=["POST"])
def api_agree_draw():
    with session.lock:
        session.result_override = {"status": "agreed_draw", "winner": None}
        session.bot_pending = False
        session.premove = None
    return jsonify(session.state())


def bot_accepts_draw() -> bool:
    with session.lock:
        board = session.board.copy(stack=True)
        key = zobrist_hash(board)
        meta = board_meta(board)
        bot_white = session.bot_color == chess.WHITE
        bot_eval = float(meta["material_balance"]) * (1.0 if bot_white else -1.0)
        halfmove = meta["halfmove_clock"]
        bot_clock = session.clocks["w" if bot_white else "b"]
    with analysis_lock:
        snap = dict(analysis_state)
    if snap.get("key") == key and snap.get("result"):
        eval_white = snap["result"].get("eval_white", 0) / 100.0
        bot_eval = eval_white if bot_white else -eval_white
    if bot_eval < -0.75 and bot_clock > 30:
        return False
    if abs(bot_eval) <= 1.0 and (halfmove >= 30 or bot_clock < 60):
        return True
    return bot_eval > -0.25


@app.route("/api/offer_draw", methods=["POST"])
def api_offer_draw():
    d = request.get_json(force=True, silent=True) or {}
    color = d.get("color", session.you_color)
    if color not in ("w", "b"):
        color = session.you_color
    with session.lock:
        if session._finished():
            return jsonify({"error": "Partie beendet"}), 400
        session.draw_offered_by = color
        if not session.bot_enabled:
            session.last_draw_offer = "pending"
        elif bot_accepts_draw():
            session.result_override = {"status": "agreed_draw", "winner": None}
            session.bot_pending = False
            session.premove = None
            session.last_draw_offer = "accepted"
        else:
            session.last_draw_offer = "declined"
    return jsonify(session.state())


@app.route("/api/abort", methods=["POST"])
def api_abort():
    with session.lock:
        if len(session.san_history) > 1:
            return jsonify({"error": "Abbruch nur vor dem 2. Zug"}), 400
        s = session.new(session.you_color, session.difficulty,
                        session.time_control, session.bot_enabled,
                        session.think_delay, session.increment,
                        dict(session.settings))
    s["aborted"] = True
    return jsonify(s)


if not LOW_RAM:
    threading.Thread(target=analysis_loop, daemon=True).start()
else:
    analysis_state.update({"thinking": False, "result": None})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Chess Bot v6.2 · host={HOST} low_ram={LOW_RAM} sims={SIMS} analysis={'off' if LOW_RAM else 'on'}")
    app.run(host=HOST, port=port, threaded=not LOW_RAM, debug=False)
