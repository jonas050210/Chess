"""Live-Statistik: Reaktion, Rewards, W/D/L, Taktiken, Engine-Snapshot."""
from __future__ import annotations

import math
import threading
import time
from collections import Counter


class StatsTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.new_game()

    def new_game(self):
        with self.lock:
            self.game_bot_moves = 0
            self.game_user_moves = 0
            self.game_reward = 0.0
            self.game_reactions: list[float] = []
            self.game_rewards: list[float] = []
            self.result_recorded = False
            self.last_result = None
            self.session_results = getattr(self, "session_results", Counter())
            self.session_bot_moves = getattr(self, "session_bot_moves", 0)
            self.session_user_moves = getattr(self, "session_user_moves", 0)
            self.session_reward = getattr(self, "session_reward", 0.0)
            self.session_reactions = getattr(self, "session_reactions", [])
            self.session_rewards = getattr(self, "session_rewards", [])
            self.tactic_counts = getattr(self, "tactic_counts", Counter())
            self.last_analysis_key = None
            self.last_reaction_ms = 0.0
            self.last_reward = 0.0
            self.started_at = time.time()

    def record_user_move(self):
        with self.lock:
            self.game_user_moves += 1
            self.session_user_moves += 1

    def record_bot_move(self, seconds: float, reward: float, uci: str = ""):
        ms = max(0.0, float(seconds) * 1000.0)
        reward = float(reward)
        with self.lock:
            self.last_reaction_ms = ms
            self.last_reward = reward
            self.game_bot_moves += 1
            self.session_bot_moves += 1
            self.game_reward += reward
            self.session_reward += reward
            self.game_reactions.append(ms)
            self.session_reactions.append(ms)
            self.game_rewards.append(reward)
            self.session_rewards.append(reward)
            if len(self.session_reactions) > 500:
                self.session_reactions = self.session_reactions[-500:]
                self.session_rewards = self.session_rewards[-500:]

    def undo_moves(self, actors: list[str]):
        """Roll back visible game/session move totals and bot reaction samples."""
        with self.lock:
            for actor in actors:
                if actor == "bot":
                    self.game_bot_moves = max(0, self.game_bot_moves - 1)
                    self.session_bot_moves = max(0, self.session_bot_moves - 1)
                    if self.game_reactions:
                        self.game_reactions.pop()
                    if self.session_reactions:
                        self.session_reactions.pop()
                    if self.game_rewards:
                        self.game_reward -= self.game_rewards.pop()
                    if self.session_rewards:
                        self.session_reward -= self.session_rewards.pop()
                elif actor == "user":
                    self.game_user_moves = max(0, self.game_user_moves - 1)
                    self.session_user_moves = max(0, self.session_user_moves - 1)
            self.last_reaction_ms = self.session_reactions[-1] if self.session_reactions else 0.0
            self.last_reward = self.session_rewards[-1] if self.session_rewards else 0.0

    def record_analysis(self, key, result: dict | None):
        if not result or key == self.last_analysis_key:
            return
        with self.lock:
            self.last_analysis_key = key
            for tag in result.get("tactics", []):
                self.tactic_counts[tag] += 1

    def record_result(self, status: str, winner: str | None, bot_color: str):
        with self.lock:
            if self.result_recorded:
                return
            self.result_recorded = True
            if winner is None:
                self.last_result = "draw"
            elif winner == bot_color:
                self.last_result = "win"
            else:
                self.last_result = "loss"
            self.session_results[self.last_result] += 1

    def undo_result(self):
        with self.lock:
            if self.result_recorded and self.last_result:
                self.session_results[self.last_result] -= 1
                self.result_recorded = False
                self.last_result = None

    @staticmethod
    def _stats(values: list[float]):
        if not values:
            return {"last": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0, "n": 0}
        return {
            "last": round(values[-1], 3),
            "avg": round(sum(values) / len(values), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "n": len(values),
        }

    def snapshot(self, state: dict, analysis: dict | None) -> dict:
        with self.lock:
            a = state.get("ai", {})
            r = state.get("rules", {})
            ana = analysis or {}
            results = dict(self.session_results)
            games = sum(results.values())
            win_rate = round((results.get("win", 0) + 0.5 * results.get("draw", 0)) / max(1, games), 3)
            reward_norm = math.tanh(self.session_reward / 10.0)
            return {
                "engine": a.get("engine", "?"),
                "arch": a.get("arch", "?"),
                "device": a.get("device", "CPU"),
                "torch": a.get("torch", False),
                "checkpoint": a.get("checkpoint", False),
                "planes": a.get("planes", 0),
                "actions": a.get("action_size", 0),
                "sims": a.get("simulations"),
                "cache": a.get("cache_size", 0),
                "reaction": self._stats(self.session_reactions),
                "reaction_game": self._stats(self.game_reactions),
                "reward": self._stats(self.session_rewards),
                "reward_game": self._stats(self.game_rewards),
                "reward_total": round(self.session_reward, 3),
                "reward_game_total": round(self.game_reward, 3),
                "reward_norm": round(reward_norm, 3),
                "results": results,
                "games": games,
                "win_rate": win_rate,
                "moves": {
                    "bot_game": self.game_bot_moves,
                    "user_game": self.game_user_moves,
                    "bot_session": self.session_bot_moves,
                    "user_session": self.session_user_moves,
                },
                "tactics": dict(self.tactic_counts),
                "reaction_history": [round(v, 2) for v in self.session_reactions[-60:]],
                "reward_history": [round(v, 3) for v in self.session_rewards[-60:]],
                "game_reward_history": [round(v, 3) for v in self.game_rewards[-60:]],
                "analysis": {
                    "depth": ana.get("depth", 0),
                    "nodes": ana.get("nodes", 0),
                    "best": ana.get("best_san", "—"),
                    "eval_white": ana.get("eval_white", 0),
                    "cp": ana.get("cp", 0),
                    "pv": ana.get("pv", []),
                    "tactics": ana.get("tactics", []),
                    "phase": ana.get("phase", "—"),
                    "legal_count": ana.get("legal_count", 0),
                    "in_check": ana.get("in_check", False),
                },
                "game": {
                    "status": state.get("status", "?"),
                    "turn": state.get("turn", "?"),
                    "ply": len(state.get("san", [])),
                    "fen": state.get("fen", ""),
                    "pgn": state.get("pgn", ""),
                    "clocks": state.get("clocks", {}),
                    "time_control": state.get("time_control", 0),
                    "increment": state.get("increment", 0),
                    "think_delay": state.get("think_delay", 0),
                    "premove": state.get("premove"),
                    "draw_offer": state.get("draw_offer"),
                    "last_move_ms": state.get("last_move_ms", 0),
                    "move_times": state.get("move_times", []),
                    "legal": state.get("rules", {}).get("legal_count", 0),
                    "bot_thinking": state.get("bot_thinking", False),
                    "material": r.get("material_balance", 0),
                    "phase": r.get("phase", "—"),
                    "castling": r.get("castling", "—"),
                    "ep": r.get("ep_square"),
                    "halfmove": r.get("halfmove_clock", 0),
                    "threefold": r.get("can_claim_threefold", False),
                    "fifty": r.get("can_claim_fifty", False),
                    "insufficient": r.get("insufficient_material", False),
                },
                "uptime_s": round(time.time() - self.started_at, 1),
            }


stats = StatsTracker()
