"""Local, browser-only chess server. Rules belong to python-chess, not the UI.

Each browser has a separate in-memory game, identified by a SameSite cookie.
Search and analysis use board snapshots outside the game lock. No training runs
from this process: see ai/train_cli.py for the terminal-only pipeline.
"""
from __future__ import annotations

import math
import os
import secrets
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit

import chess
from flask import Flask, g, jsonify, request, send_from_directory

from ai import ACTION_SIZE, HIDDEN, PLANES, HAS_TORCH, board_meta
from ai.analysis import AnalysisEngine
from ai.baseline import BaselineBot
from ai.bot import AIBot, SIMS
from ai.mcts import position_key
from ai.stats import StatsTracker
import ai.bot as bot_mod

LOW_RAM = os.environ.get("CHESS_LOW_RAM") == "1"
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

ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4}
PROMO_MAP = {"q": chess.QUEEN, "r": chess.ROOK,
             "b": chess.BISHOP, "n": chess.KNIGHT}
THEMES = {"duo", "green", "blue", "brown", "sand", "midnight"}
HIGHLIGHTS = {"yellow", "blue", "red"}
BOOL_SETTINGS = {"coords", "animation", "auto_queen", "premove", "texture", "arrows", "flip"}
VIEW_SETTINGS = BOOL_SETTINGS | {"theme", "highlight"}
CONFIG_FIELDS = VIEW_SETTINGS | {"difficulty", "bot_enabled", "think_delay",
                                 "time_control", "increment", "settings"}


def captured_material(board: chess.Board) -> dict:
    """Actual captured pieces by capturing color, not missing pieces.

    Material-count subtraction falsely reports a promoted pawn as a capture,
    and can hide a captured promoted queen. Replaying the moves also handles
    en passant (the victim was not on the destination square) and undo.
    """
    out = {"w": [], "b": []}
    replay = board.root()
    for move in board.move_stack:
        if replay.is_capture(move):
            victim = (chess.Piece(chess.PAWN, not replay.turn)
                      if replay.is_en_passant(move) else replay.piece_at(move.to_square))
            if victim is not None:
                out["w" if replay.turn else "b"].append(victim.symbol())
        replay.push(move)
    for color in out:
        out[color].sort(key=lambda s: ORDER.get(s.upper(), 9))
    return out


def pgn_from_san(san: list[str]) -> str:
    return " ".join(f"{i // 2 + 1}. {san[i]}" +
                    (f" {san[i + 1]}" if i + 1 < len(san) else "")
                    for i in range(0, len(san), 2))


def get_json_object() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def number(value, name: str, lo: float, hi: float, integer: bool = False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number")
    if integer and int(value) != value:
        raise ValueError(f"{name} must be a whole number")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}")
    return int(value) if integer else float(value)


def boolean(value, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be true or false")
    return value


def validated_config(data: dict) -> dict:
    unknown = set(data) - CONFIG_FIELDS
    if unknown:
        raise ValueError(f"Unknown setting: {sorted(unknown)[0]}")
    result = {}
    options = {key: data[key] for key in VIEW_SETTINGS if key in data}
    if "settings" in data:
        if not isinstance(data["settings"], dict):
            raise ValueError("settings must be a JSON object")
        options.update(data["settings"])
    unknown = set(options) - VIEW_SETTINGS
    if unknown:
        raise ValueError(f"Unknown display setting: {sorted(unknown)[0]}")
    for key, value in options.items():
        if key in BOOL_SETTINGS:
            options[key] = boolean(value, key)
        elif key == "theme" and (not isinstance(value, str) or value not in THEMES):
            raise ValueError("Invalid theme")
        elif key == "highlight" and (not isinstance(value, str) or value not in HIGHLIGHTS):
            raise ValueError("Invalid highlight color")
    result["settings"] = options
    if "difficulty" in data:
        result["difficulty"] = number(data["difficulty"], "difficulty", 1, 5, True)
    if "bot_enabled" in data:
        result["bot_enabled"] = boolean(data["bot_enabled"], "bot_enabled")
    if "think_delay" in data:
        result["think_delay"] = number(data["think_delay"], "think_delay", 0, 5)
    if "time_control" in data:
        result["time_control"] = number(data["time_control"], "time_control", 30, 86400)
    if "increment" in data:
        result["increment"] = number(data["increment"], "increment", 0, 30)
    return result


class Session:
    """One browser's game. Mutable board/clock state is guarded by self.lock."""

    def __init__(self):
        self.lock = threading.RLock()
        self.engine_lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.analysis_compute_lock = threading.Lock()
        self.stats = StatsTracker()
        self.bot = AIBot(checkpoint=NP_CKPT, torch_checkpoint=TORCH_CKPT)
        self.fallback = BaselineBot()
        self.analysis_engine = AnalysisEngine()
        self.analysis_state = {"key": None, "result": None, "thinking": False, "updated": 0.0}
        self.version = 0
        self.engine_epoch = 0
        self.searched_epoch = -1
        self.settings = {"theme": "duo", "highlight": "yellow", "coords": True,
                         "animation": True, "auto_queen": False, "premove": True,
                         "texture": False, "arrows": True, "flip": False}
        self.new()

    def _finished(self) -> bool:
        # A *claimable* threefold/50-move draw must never end the game by itself.
        return (self.result_override is not None or self.timed_out is not None or
                self.board.outcome(claim_draw=False) is not None)

    def _tick(self):
        now = time.time()
        elapsed = max(0.0, now - self.last_tick)
        self.last_tick = now
        if self.clock_started and not self._finished():
            color = "w" if self.board.turn else "b"
            self.clocks[color] = max(0.0, self.clocks[color] - elapsed)
            if self.clocks[color] <= 0:
                opponent = not self.board.turn
                winner = None if self.board.has_insufficient_material(opponent) else (
                    "w" if opponent else "b")
                self.timed_out = {"status": "timeout", "winner": winner}
                self.bot_pending = False
                self.premove = None
                self.version += 1  # invalidate any search already running

    def _apply(self, move: chess.Move) -> bool:
        # Undo restores the clock at the start of the move, including increments.
        clock_before = dict(self.clocks)
        self._tick()
        if self._finished() or not self.board.is_legal(move):
            return False
        mover = "w" if self.board.turn else "b"
        san = self.board.san(move)
        elapsed = time.time() - self.last_move_started_at if self.clock_started else 0.0
        self.board.push(move)
        self.actor_history.append("bot" if self.bot_enabled and
                                  mover == ("w" if self.bot_color else "b") else "user")
        self.clock_history.append(clock_before)
        self.clocks[mover] = max(0.0, self.clocks[mover] + self.increment)
        self.move_history.append(move)
        self.san_history.append(san)
        self.last_move = move
        self.last_move_ms = max(0.0, elapsed * 1000.0)
        self.move_times.append(round(self.last_move_ms, 1))
        self.started = True
        self.last_tick = self.last_move_started_at = time.time()
        self.version += 1
        # An offer remains open through the offerer's move, and is declined
        # when the opponent chooses a move instead of accepting.
        if self.draw_offered_by != mover or self.last_draw_offer != "pending":
            self.last_draw_offer = None
            self.draw_offered_by = None
        return True

    def _find_move(self, frm: str, to: str, promotion: str = "q"):
        try:
            source, dest = chess.parse_square(frm), chess.parse_square(to)
        except (ValueError, TypeError):
            return None
        target = PROMO_MAP.get(promotion)
        if target is None:
            return None
        for move in self.board.legal_moves:
            if move.from_square == source and move.to_square == dest and (
                    not move.promotion or move.promotion == target):
                return move
        return None

    def set_premove(self, frm: str, to: str, promotion: str = "q") -> bool:
        if (not self.bot_enabled or not self.bot_pending or self.board.turn == self.you or
                not self.settings["premove"] or self._finished()):
            return False
        try:
            source, dest = chess.parse_square(frm), chess.parse_square(to)
        except (ValueError, TypeError):
            return False
        piece = self.board.piece_at(source)
        if (source == dest or piece is None or piece.color != self.you or
                not isinstance(promotion, str) or promotion not in PROMO_MAP):
            return False
        self.premove = {"from": frm, "to": to, "promotion": promotion}
        return True

    def premove_uci(self):
        if not self.premove:
            return None
        return (self.premove["from"] + self.premove["to"] +
                (self.premove["promotion"] if self.premove["promotion"] != "q" else ""))

    def _schedule_bot(self) -> bool:
        if (self.bot_enabled and not self._finished() and
                self.board.turn == self.bot_color and not self.bot_pending):
            self.bot_pending = True
            self.bot_requested_at = time.time()
            token = self.version
            delay = self.think_delay
            threading.Thread(target=self._bot_async, args=(token, delay), daemon=True).start()
            return True
        return False

    def _bot_async(self, token: int, delay: float):
        if delay:
            time.sleep(delay)
        with self.lock:
            if (token != self.version or not self.bot_pending or not self.bot_enabled or
                    self.board.turn != self.bot_color or self._finished()):
                return
            board = self.board.copy(stack=True)
            level, epoch, started_at = self.difficulty, self.engine_epoch, self.bot_requested_at
        start = time.perf_counter()
        try:
            with self.engine_lock:
                if self.searched_epoch != epoch:
                    self.bot.reset()
                    self.searched_epoch = epoch
                if token != self.version:
                    return
                move = self.bot.choose_move(board, level, cancel=lambda: token != self.version)
        except Exception:
            app.logger.exception("Bot search failed; using fallback")
            try:
                move = self.fallback.choose_move(board, 1, cancel=lambda: token != self.version)
            except Exception:
                app.logger.exception("Fallback search failed; using a legal move")
                move = None
        elapsed = time.perf_counter() - start
        with self.lock:
            if (token != self.version or not self.bot_pending or not self.bot_enabled or
                    self.board.turn != self.bot_color or self._finished()):
                return
            if move is None or not self.board.is_legal(move):
                move = next(iter(self.board.legal_moves), None)
            if move is not None and self._apply(move):
                self.last_bot_move = move.uci()
                reaction = max(elapsed, time.time() - started_at)
                self.stats.record_bot_move(reaction, 0.0, move.uci())
            self.bot_pending = False
            if self.premove and not self._finished() and self.board.turn == self.you:
                queued, self.premove = self.premove, None
                candidate = self._find_move(queued["from"], queued["to"], queued["promotion"])
                if candidate is not None and self._apply(candidate):
                    self.stats.record_user_move()
            self._schedule_bot()

    def apply_settings(self, data: dict):
        cfg = validated_config(data)
        with self.lock:
            options = cfg["settings"]
            self.settings.update(options)
            if "difficulty" in cfg:
                self.difficulty = cfg["difficulty"]
            if "think_delay" in cfg:
                self.think_delay = cfg["think_delay"]
            if "time_control" in cfg:
                self.time_control = cfg["time_control"]
                if not self.started:
                    self.clocks = {"w": self.time_control, "b": self.time_control}
            if "increment" in cfg:
                self.increment = cfg["increment"]
            if "bot_enabled" in cfg:
                self.bot_enabled = cfg["bot_enabled"]
            if not self.bot_enabled or not self.settings["premove"]:
                self.premove = None
            if self.bot_pending and ("difficulty" in cfg or "bot_enabled" in cfg):
                self.bot_pending = False
                self.version += 1
            self._schedule_bot()

    def new(self, you_color="w", difficulty=3, time_control=600,
            bot_enabled=True, think_delay=0.6, increment=0, settings=None):
        # Also validate direct callers: never leave a partially initialized game.
        if you_color not in ("w", "b"):
            raise ValueError("you_color must be w or b")
        cfg = validated_config({"difficulty": difficulty, "time_control": time_control,
                                "bot_enabled": bot_enabled, "think_delay": think_delay,
                                "increment": increment, "settings": settings or {}})
        with self.lock:
            self.version += 1
            self.engine_epoch += 1
            self.board = chess.Board()
            self.you_color = you_color
            self.you = you_color == "w"
            self.bot_color = not self.you
            self.difficulty = cfg["difficulty"]
            self.time_control = cfg["time_control"]
            self.increment = cfg["increment"]
            self.think_delay = cfg["think_delay"]
            self.settings.update(cfg["settings"])
            self.settings["flip"] = you_color == "b"
            self.clocks = {"w": self.time_control, "b": self.time_control}
            self.clock_history: list[dict[str, float]] = []
            self.move_history: list[chess.Move] = []
            self.actor_history: list[str] = []
            self.san_history: list[str] = []
            self.last_move = None
            self.last_move_ms = 0.0
            self.move_times: list[float] = []
            self.started = False
            self.clock_started = True
            self.last_tick = self.last_move_started_at = time.time()
            self.bot_enabled = cfg["bot_enabled"]
            self.bot_pending = False
            self.bot_requested_at = None
            self.last_bot_move = None
            self.result_override = None
            self.timed_out = None
            self.result_recorded = False
            self.premove = None
            self.draw_offered_by = None
            self.last_draw_offer = None
            self.stats.new_game()
            with self.analysis_lock:
                self.analysis_state = {"key": None, "result": None,
                                       "thinking": False, "updated": 0.0}
            self._schedule_bot()
            return self.state()

    def state(self, extra: dict | None = None) -> dict:
        with self.lock:
            self._tick()
            outcome = self.board.outcome(claim_draw=False)
            status, winner = "playing", None
            if self.result_override:
                status, winner = self.result_override["status"], self.result_override["winner"]
            elif self.timed_out:
                status, winner = self.timed_out["status"], self.timed_out["winner"]
            elif outcome is not None:
                status = outcome.termination.name.lower()
                winner = ("w" if outcome.winner else "b") if outcome.winner is not None else None
            elif self.board.is_check():
                status = "check"
            if self._finished() and not self.result_recorded:
                self.stats.record_result(status, winner, "w" if self.bot_color else "b")
                self.result_recorded = True
            king = self.board.king(self.board.turn) if self.board.is_check() else None
            data = {
                "fen": self.board.fen(),
                "turn": "w" if self.board.turn else "b",
                "legal": [move.uci() for move in self.board.legal_moves],
                "last_move": self.last_move.uci() if self.last_move else None,
                "san": list(self.san_history), "pgn": pgn_from_san(self.san_history),
                "status": status, "winner": winner,
                "check": self.board.is_check(),
                "check_square": chess.square_name(king) if king is not None else None,
                "captured": captured_material(self.board),
                "clocks": {key: round(value, 2) for key, value in self.clocks.items()},
                "you_color": self.you_color, "bot_color": "w" if self.bot_color else "b",
                "difficulty": self.difficulty, "bot_enabled": self.bot_enabled,
                "bot_thinking": self.bot_pending, "last_bot_move": self.last_bot_move,
                "think_delay": self.think_delay, "started": self.started,
                "clock_started": self.clock_started, "time_control": self.time_control,
                "increment": self.increment, "premove": self.premove_uci(),
                "draw_offer": self.last_draw_offer,
                "draw_offered_by": self.draw_offered_by,
                "last_move_ms": round(self.last_move_ms, 1),
                "move_times": list(self.move_times[-20:]), "settings": dict(self.settings),
                "rules": board_meta(self.board),
                "ai": {"engine": self.bot.engine,
                       "checkpoint": self.bot.has_checkpoint,
                       "device": self.bot.device, "torch": HAS_TORCH,
                       "planes": PLANES, "action_size": ACTION_SIZE, "hidden": HIDDEN,
                       "arch": "ResNet" if self.bot.engine == "torch-mcts" else (
                           f"MLP {HIDDEN}" if self.bot.has_checkpoint else "Alpha-beta search"),
                       "cache_size": self.bot.cache_size,
                       "simulations": SIMS[self.difficulty] if self.bot.has_checkpoint else None},
            }
            if extra:
                data.update(extra)
            return data

    def analysis_snapshot(self) -> dict:
        with self.lock:
            self._tick()
            board = self.board.copy(stack=True)
            key, finished = position_key(board), self._finished()
        if LOW_RAM or finished:
            return {"fen": board.fen(), "finished": finished,
                    "thinking": False, "depth": 0, "result": None, "updated": 0}
        with self.analysis_lock:
            if self.analysis_state["key"] != key:
                self.analysis_state = {"key": key, "result": None,
                                       "thinking": True, "updated": 0.0}
                threading.Thread(target=self._analyze_async,
                                 args=(board, key), daemon=True).start()
            snapshot = dict(self.analysis_state)
        result = snapshot["result"]
        return {"fen": board.fen(), "finished": False,
                "thinking": snapshot["thinking"],
                "depth": result["depth"] if result else 0,
                "result": result, "updated": snapshot["updated"]}

    def _analyze_async(self, board: chess.Board, key):
        try:
            with self.analysis_compute_lock:
                result = self.analysis_engine.analyze(board, max_depth=3)
        except Exception:
            app.logger.exception("Analysis failed")
            result = None
        with self.analysis_lock:
            if self.analysis_state["key"] == key:
                self.analysis_state.update({"result": result, "thinking": False,
                                            "updated": time.time()})
                self.stats.record_analysis(key, result)


class SessionStore:
    """Small bounded store. A cookie identifies a game; never store game data in it."""

    def __init__(self, capacity=32, ttl_seconds=6 * 3600):
        self.lock = threading.Lock()
        self.games: OrderedDict[str, tuple[Session, float]] = OrderedDict()
        self.capacity, self.ttl_seconds = capacity, ttl_seconds

    def get(self, sid: str | None) -> tuple[str, Session, bool]:
        now = time.time()
        with self.lock:
            for key, (_, seen) in list(self.games.items()):
                if now - seen > self.ttl_seconds:
                    del self.games[key]
            if sid and sid in self.games:
                game, _ = self.games.pop(sid)
                self.games[sid] = (game, now)
                return sid, game, False
            while len(self.games) >= self.capacity:
                self.games.popitem(last=False)
            sid = secrets.token_urlsafe(32)
            game = Session()
            self.games[sid] = (game, now)
            return sid, game, True


store = SessionStore()


@app.before_request
def protect_and_select_game():
    # Localhost-only by default. If CHESS_HOST=0.0.0.0, use a trusted LAN or
    # Arena's preview; this is NOT an Internet-facing authenticated service.
    if HOST in ("127.0.0.1", "localhost", "::1"):
        host = urlsplit(f"//{request.host}").hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return jsonify({"error": "Invalid Host"}), 400
    if request.method == "POST":
        if request.mimetype != "application/json":
            return jsonify({"error": "Content-Type must be application/json"}), 415
        origin = request.headers.get("Origin")
        # Compare authorities, not the backend's scheme: HTTPS is terminated by
        # the Arena/LAN reverse proxy and Flask may see an HTTP request.
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            return jsonify({"error": "Cross-origin request rejected"}), 403
    # In an embedded preview, browsers may block third-party cookies. The web
    # client keeps this unguessable ID in sessionStorage and sends it same-origin.
    sid, game, is_new = store.get(request.headers.get("X-Game-ID") or
                                  request.cookies.get("chess_sid"))
    g.game_id, g.game, g.new_game_cookie = sid, game, is_new
    return None


@app.after_request
def response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'")
    if getattr(g, "game_id", None):
        response.headers["X-Game-ID"] = g.game_id
    if getattr(g, "new_game_cookie", False):
        response.set_cookie("chess_sid", g.game_id, httponly=True, samesite="Strict",
                            secure=request.is_secure, max_age=store.ttl_seconds)
    return response


@app.errorhandler(ValueError)
def invalid_input(error):
    return jsonify({"error": str(error)}), 400


@app.route("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory(WEB, path)


@app.route("/api/state")
def api_state():
    return jsonify(g.game.state())


@app.route("/api/analysis")
def api_analysis():
    return jsonify(g.game.analysis_snapshot())


@app.route("/api/stats")
def api_stats():
    game = g.game
    state = game.state()
    with game.analysis_lock:
        snap = dict(game.analysis_state)
    with game.lock:
        key = position_key(game.board)
    result = snap["result"] if snap["key"] == key else None
    return jsonify(game.stats.snapshot(state, result))


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    game = g.game
    if request.method == "POST":
        game.apply_settings(get_json_object())
    return jsonify(game.state())


@app.route("/api/config", methods=["POST"])
def api_config():
    g.game.apply_settings(get_json_object())
    return jsonify(g.game.state())


@app.route("/api/new", methods=["POST"])
def api_new():
    data = get_json_object()
    unknown = set(data) - (CONFIG_FIELDS | {"you_color"})
    if unknown:
        raise ValueError(f"Unknown game setting: {sorted(unknown)[0]}")
    cfg = validated_config({key: value for key, value in data.items()
                            if key != "you_color"})
    return jsonify(g.game.new(data.get("you_color", "w"), cfg.get("difficulty", 3),
                              cfg.get("time_control", 600), cfg.get("bot_enabled", True),
                              cfg.get("think_delay", .6), cfg.get("increment", 0),
                              cfg["settings"]))


@app.route("/api/move", methods=["POST"])
def api_move():
    data = get_json_object()
    game = g.game
    promotion = data.get("promotion", "q")
    if not isinstance(promotion, str) or promotion not in PROMO_MAP:
        raise ValueError("Invalid promotion piece")
    frm, to = data.get("from", ""), data.get("to", "")
    with game.lock:
        if game._finished():
            return jsonify({"error": "Game is over"}), 400
        if game.bot_enabled and game.board.turn != game.you:
            game._tick()
            if game._finished():
                return jsonify({"error": "Game is over"}), 400
            if data.get("premove") and game.set_premove(frm, to, promotion):
                return jsonify(game.state({"premove_set": game.premove_uci()}))
            return jsonify({"error": "Wait for the bot or queue a premove"}), 400
        move = game._find_move(frm, to, promotion)
        if move is None:
            return jsonify({"error": "Illegal move"}), 400
        if not game._apply(move):
            return jsonify({"error": "Time has run out"}), 400
        game.stats.record_user_move()
        game._schedule_bot()
        return jsonify(game.state({"your_move": move.uci()}))


@app.route("/api/premove", methods=["POST"])
def api_premove():
    data, game = get_json_object(), g.game
    with game.lock:
        game._tick()
        if data.get("cancel") is True:
            game.premove = None
        elif not game.set_premove(data.get("from", ""), data.get("to", ""),
                                  data.get("promotion", "q")):
            return jsonify({"error": "Cannot queue that premove"}), 400
        return jsonify(game.state())


@app.route("/api/hint", methods=["POST"])
def api_hint():
    game = g.game
    get_json_object()
    with game.lock:
        game._tick()
        if game._finished() or (game.bot_enabled and game.board.turn != game.you):
            return jsonify({"error": "Wait for your turn"}), 400
        board, token, level, epoch = (game.board.copy(stack=True), game.version,
                                      game.difficulty, game.engine_epoch)
    with game.engine_lock:
        if game.searched_epoch != epoch:
            game.bot.reset()
            game.searched_epoch = epoch
        move = game.bot.hint(board, level, cancel=lambda: game.version != token)
    with game.lock:
        if token != game.version or game._finished():
            return jsonify({"error": "Position changed; try again"}), 409
        if move is None or not board.is_legal(move):
            return jsonify({"error": "No hint available"}), 400
        return jsonify({"uci": move.uci(), "san": board.san(move)})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    get_json_object()
    game = g.game
    with game.lock:
        if not game.move_history:
            return jsonify({"error": "No move to undo"}), 400
        # If the bot has answered, rewind its reply and the human move. If
        # the human just moved and the bot is still thinking, rewind only that
        # move so the human can choose a different one immediately.
        count = (2 if game.bot_enabled and len(game.move_history) >= 2 and
                 game.actor_history[-1] == "bot" and
                 game.actor_history[-2] == "user" else 1)
        undone_actors = []
        for _ in range(count):
            game.board.pop()
            game.move_history.pop()
            undone_actors.append(game.actor_history.pop())
            game.san_history.pop()
            game.clocks = game.clock_history.pop()
            game.move_times.pop()
        game.stats.undo_moves(undone_actors)
        game.last_move = game.move_history[-1] if game.move_history else None
        game.last_move_ms = game.move_times[-1] if game.move_times else 0.0
        game.last_tick = game.last_move_started_at = time.time()
        game.started = bool(game.move_history)
        game.result_override = game.timed_out = None
        if game.result_recorded:
            game.stats.undo_result()
        game.result_recorded = False
        game.bot_pending = False
        game.last_bot_move = None
        game.premove = None
        game.draw_offered_by = game.last_draw_offer = None
        game.version += 1
        game.engine_epoch += 1
        game._schedule_bot()
        return jsonify(game.state())


@app.route("/api/resign", methods=["POST"])
def api_resign():
    data, game = get_json_object(), g.game
    with game.lock:
        game._tick()
        if game._finished():
            return jsonify({"error": "Game is over"}), 400
        color = data.get("color", game.you_color if game.bot_enabled else
                         ("w" if game.board.turn else "b"))
        if color not in ("w", "b") or (game.bot_enabled and color != game.you_color):
            raise ValueError("Invalid resigning side")
        game.result_override = {"status": "resignation", "winner": "b" if color == "w" else "w"}
        game.bot_pending = False
        game.premove = None
        game.version += 1
        return jsonify(game.state())


@app.route("/api/claim_draw", methods=["POST"])
def api_claim_draw():
    get_json_object()
    game = g.game
    with game.lock:
        game._tick()
        if game._finished():
            return jsonify({"error": "Game is over"}), 400
        # Only the player whose turn it is may claim a repetition/50-move
        # draw. In a bot game the client must not claim on the bot's behalf.
        if game.bot_enabled and game.board.turn != game.you:
            return jsonify({"error": "Wait for your turn to claim a draw"}), 400
        if not (game.board.can_claim_threefold_repetition() or
                game.board.can_claim_fifty_moves()):
            return jsonify({"error": "No draw can be claimed yet"}), 400
        game.result_override = {"status": "claimed_draw", "winner": None}
        game.bot_pending = False
        game.premove = None
        game.version += 1
        return jsonify(game.state())


@app.route("/api/agree_draw", methods=["POST"])
def api_agree_draw():
    data, game = get_json_object(), g.game
    with game.lock:
        game._tick()
        if (game.bot_enabled or game._finished() or game.last_draw_offer != "pending" or
                game.draw_offered_by is None):
            return jsonify({"error": "No opponent's draw offer to accept"}), 400
        color = data.get("color")
        if color not in ("w", "b") or color == game.draw_offered_by:
            raise ValueError("Only the opponent can accept a draw offer")
        game.result_override = {"status": "agreed_draw", "winner": None}
        game.draw_offered_by = None
        game.last_draw_offer = "accepted"
        game.bot_pending = False
        game.premove = None
        game.version += 1
        return jsonify(game.state())


def bot_accepts_draw(game: Session) -> bool:
    meta = board_meta(game.board)
    advantage = meta["material_balance"] * (1 if game.bot_color else -1)
    # Decline while ahead; accept a genuinely even late position or low clock.
    remaining = game.clocks["w" if game.bot_color else "b"]
    return advantage <= 0.5 and (meta["halfmove_clock"] >= 35 or remaining < 45)


@app.route("/api/offer_draw", methods=["POST"])
def api_offer_draw():
    data, game = get_json_object(), g.game
    with game.lock:
        game._tick()
        if game._finished():
            return jsonify({"error": "Game is over"}), 400
        color = data.get("color", game.you_color if game.bot_enabled else
                         ("w" if game.board.turn else "b"))
        if color not in ("w", "b") or (game.bot_enabled and color != game.you_color):
            raise ValueError("Invalid offering side")
        game.draw_offered_by = color
        if not game.bot_enabled:
            game.last_draw_offer = "pending"
        elif bot_accepts_draw(game):
            game.result_override = {"status": "agreed_draw", "winner": None}
            game.bot_pending = False
            game.premove = None
            game.version += 1
            game.last_draw_offer = "accepted"
        else:
            game.last_draw_offer = "declined"
        return jsonify(game.state())


@app.route("/api/abort", methods=["POST"])
def api_abort():
    get_json_object()
    game = g.game
    with game.lock:
        game._tick()
        if game._finished():
            return jsonify({"error": "Game is over"}), 400
        if len(game.san_history) > 1:
            return jsonify({"error": "Only unstarted games can be aborted"}), 400
        result = game.new(game.you_color, game.difficulty, game.time_control,
                          game.bot_enabled, game.think_delay, game.increment,
                          dict(game.settings))
        result["aborted"] = True
        return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Chess Garden · browser at http://{HOST}:{port} · low RAM={LOW_RAM}")
    # Threading remains on in low-RAM mode: a search must not block the API.
    app.run(host=HOST, port=port, threaded=True, debug=False)
