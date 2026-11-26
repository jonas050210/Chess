import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import chess

from ai.mcts import position_key
from ai.train_cli import atomic_copy, paired_delta
from server import Session, app, session as live_session


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.session.new(bot_enabled=False)

    def test_clock_runs_before_first_move(self):
        before = self.session.clocks["w"]
        self.session.last_tick = time.time() - 0.25
        self.session._tick()
        self.assertLess(self.session.clocks["w"], before)
        self.assertFalse(self.session.started)

    def test_first_move_time_is_recorded(self):
        now = time.time()
        self.session.last_tick = now - 1.0
        self.session.last_move_started_at = now - 1.0
        self.assertTrue(self.session._apply(chess.Move.from_uci("e2e4")))
        self.assertGreaterEqual(self.session.last_move_ms, 900.0)

    def test_flagged_player_cannot_apply_move(self):
        self.session.clocks["w"] = 0.05
        self.session.last_tick = time.time() - 0.2
        self.assertFalse(self.session._apply(chess.Move.from_uci("e2e4")))
        self.assertEqual(self.session.san_history, [])
        self.assertEqual(self.session.timed_out["winner"], "b")


class ClockApiTests(unittest.TestCase):
    def test_legal_move_updates_game_state(self):
        live_session.new(bot_enabled=False)
        response = app.test_client().post(
            "/api/move", json={"from": "e2", "to": "e4"}
        )
        self.assertEqual(response.status_code, 200)
        state = response.get_json()
        self.assertEqual(state["san"], ["e4"])
        self.assertEqual(state["turn"], "b")
        self.assertEqual(state["status"], "playing")

    def test_api_rejects_simple_cross_site_posts(self):
        client = app.test_client()
        simple = client.post("/api/new", data='{"you_color":"w"}',
                             content_type="text/plain")
        self.assertEqual(simple.status_code, 415)
        cross_origin = client.post(
            "/api/new", json={"you_color": "w"},
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(cross_origin.status_code, 403)
        bad_host = client.post("/api/new", json={}, headers={"Host": "attacker.example"})
        self.assertEqual(bad_host.status_code, 400)

    def test_api_rejects_move_after_flag_fall(self):
        live_session.new(bot_enabled=False)
        live_session.clocks["w"] = 0.05
        live_session.last_tick = time.time() - 0.2
        response = app.test_client().post(
            "/api/move", json={"from": "e2", "to": "e4"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(live_session.san_history, [])
        self.assertEqual(live_session.state()["status"], "timeout")


class SearchStateTests(unittest.TestCase):
    def test_cache_key_distinguishes_model_clock_inputs(self):
        a = chess.Board()
        b = chess.Board()
        b.halfmove_clock = 42
        self.assertEqual(chess.polyglot.zobrist_hash(a), chess.polyglot.zobrist_hash(b))
        self.assertNotEqual(position_key(a), position_key(b))

    def test_cache_key_distinguishes_repetition_history(self):
        fresh = chess.Board()
        repeated = chess.Board()
        cycle = ["g1f3", "g8f6", "f3g1", "f6g8"]
        for uci in cycle * 2:
            repeated.push_uci(uci)
        repeated.halfmove_clock = fresh.halfmove_clock
        self.assertEqual(chess.polyglot.zobrist_hash(fresh),
                         chess.polyglot.zobrist_hash(repeated))
        self.assertNotEqual(position_key(fresh), position_key(repeated))

    def test_paired_gate_uses_paired_games(self):
        current = {"game_scores": [0.5, 0.0, 1.0, 0.5]}
        improved = {"game_scores": [1.0, 0.5, 1.0, 1.0]}
        mean, lower, n = paired_delta(improved, current)
        self.assertEqual(n, 4)
        self.assertAlmostEqual(mean, 0.375)
        self.assertLessEqual(lower, mean)


class AtomicPromotionTests(unittest.TestCase):
    def test_atomic_copy_replaces_complete_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, dst = root / "candidate", root / "active"
            src.write_bytes(b"new checkpoint")
            dst.write_bytes(b"old checkpoint")
            atomic_copy(src, dst)
            self.assertEqual(dst.read_bytes(), b"new checkpoint")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["active", "candidate"])

    def test_failed_copy_leaves_active_checkpoint_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, dst = root / "candidate", root / "active"
            src.write_bytes(b"new checkpoint")
            dst.write_bytes(b"known good")
            with patch("ai.train_cli.shutil.copy2", side_effect=OSError("simulated failure")):
                with self.assertRaises(OSError):
                    atomic_copy(src, dst)
            self.assertEqual(dst.read_bytes(), b"known good")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["active", "candidate"])


if __name__ == "__main__":
    unittest.main()
