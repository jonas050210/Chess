"""Rules, search concurrency and training gate regression tests (no GUI needed)."""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import chess

from ai.baseline import BaselineBot, INF, MATE, _tt_key
from ai.bot import AIBot, approved_checkpoint
from ai.evaluate import play_game, evaluate_vs_baseline
from ai.lessons import TRAIN, HOLDOUT, synthetic_lessons, verify_lessons
from ai.mcts import position_key
from ai.train_basics import examples, rows
from ai.train_cli import ACTIVE_NPZ, ROOT, approve_checkpoint, atomic_copy, paired_delta, run_step
from ai.train_paths import candidate_output
from server import Session, app, store


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.game = Session()
        self.game.new(bot_enabled=False)

    def test_clock_runs_before_first_move(self):
        before = self.game.clocks['w']
        self.game.last_tick = time.time() - .25
        self.game._tick()
        self.assertLess(self.game.clocks['w'], before)
        self.assertFalse(self.game.started)

    def test_first_move_time_is_recorded(self):
        self.game.last_tick = self.game.last_move_started_at = time.time() - 1
        self.assertTrue(self.game._apply(chess.Move.from_uci('e2e4')))
        self.assertGreaterEqual(self.game.last_move_ms, 900)

    def test_flagged_player_cannot_move(self):
        self.game.clocks['w'] = .05
        self.game.last_tick = time.time() - .2
        self.assertFalse(self.game._apply(chess.Move.from_uci('e2e4')))
        self.assertEqual(self.game.san_history, [])
        self.assertEqual(self.game.timed_out['winner'], 'b')

    def test_flag_draw_when_opponent_cannot_mate(self):
        self.game.board = chess.Board('4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1')
        self.game.clocks['w'] = .01
        self.game.last_tick -= .3
        self.game._tick()
        self.assertIsNone(self.game.timed_out['winner'])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.get('/api/state')
        self.sid = self.client.get_cookie('chess_sid').value
        self.game = store.games[self.sid][0]
        self.game.new(bot_enabled=False)

    def tearDown(self):
        with store.lock:
            store.games.pop(self.sid, None)

    def post(self, path, **data):
        return self.client.post(path, json=data)

    def test_client_games_are_isolated_and_work_without_cookies(self):
        self.assertEqual(self.post('/api/move', **{'from':'e2','to':'e4'}).status_code, 200)
        other = app.test_client(use_cookies=False)
        response = other.get('/api/state')
        self.assertEqual(response.json['san'], [])
        no_cookie_id = response.headers['X-Game-ID']
        second = other.get('/api/state', headers={'X-Game-ID':no_cookie_id})
        self.assertEqual(second.headers['X-Game-ID'], no_cookie_id)
        self.assertNotEqual(self.client.get('/api/state').json['fen'], second.json['fen'])
        with store.lock:
            store.games.pop(no_cookie_id, None)

    def test_legal_move_and_illegal_promotion(self):
        move = self.post('/api/move', **{'from':'e2','to':'e4'})
        self.assertEqual(move.status_code, 200)
        self.assertEqual(move.json['san'], ['e4'])
        self.assertEqual(move.json['turn'], 'b')
        self.assertEqual(self.post('/api/move', **{'from':'e7','to':'e5',
                                                   'promotion':'k'}).status_code, 400)

    def test_reject_cross_origin_malformed_and_bogus_settings(self):
        simple = self.client.post('/api/new', data='{}', content_type='text/plain')
        self.assertEqual(simple.status_code, 415)
        cross = self.client.post('/api/new', json={},
                                 headers={'Origin':'https://attacker.example'})
        self.assertEqual(cross.status_code, 403)
        host = self.client.post('/api/new', json={}, headers={'Host':'attacker.example'})
        self.assertEqual(host.status_code, 400)
        self.assertEqual(self.post('/api/settings', difficulty='bad').status_code, 400)
        self.assertEqual(self.post('/api/settings', bot_enabled='false').status_code, 400)
        self.assertEqual(self.post('/api/settings', time_control=float('inf')).status_code, 400)
        self.assertEqual(self.post('/api/settings', settings={'theme':{'fake':'duo'}}).status_code, 400)
        self.assertEqual(self.post('/api/move', **{'from':'e2','to':'e4','promotion':[]}).status_code, 400)
        self.assertFalse(self.game.bot_enabled)
        origin = self.client.post('/api/new', json={'bot_enabled':False},
                                  headers={'Origin':'https://localhost:9000'})
        self.assertEqual(origin.status_code, 403)
        with self.client.get('/') as page:
            self.assertIn('Content-Security-Policy', page.headers)

    def test_claimable_repetition_does_not_automatically_end_game(self):
        for uci in ['g1f3','g8f6','f3g1','f6g8'] * 2:
            with self.game.lock:
                self.assertTrue(self.game._apply(chess.Move.from_uci(uci)))
        state = self.client.get('/api/state').json
        self.assertTrue(state['rules']['can_claim_threefold'])
        self.assertEqual(state['status'], 'playing')
        claim = self.post('/api/claim_draw')
        self.assertEqual(claim.status_code, 200)
        self.assertEqual(claim.json['status'], 'claimed_draw')
        self.assertEqual(self.post('/api/move', **{'from':'e2','to':'e4'}).status_code, 400)

    def test_fivefold_and_seventyfive_moves_end_automatically(self):
        for uci in ['g1f3', 'g8f6', 'f3g1', 'f6g8'] * 4:
            with self.game.lock:
                self.assertTrue(self.game._apply(chess.Move.from_uci(uci)))
        self.assertEqual(self.client.get('/api/state').json['status'], 'fivefold_repetition')
        self.game.new(bot_enabled=False)
        with self.game.lock:
            self.game.board = chess.Board('4k3/8/8/8/8/8/8/R3K3 w - - 149 1')
        last = self.post('/api/move', **{'from':'a1', 'to':'a2'})
        self.assertEqual(last.status_code, 200)
        self.assertEqual(last.json['status'], 'seventyfive_moves')

    def test_50_move_claim_still_requires_click(self):
        with self.game.lock:
            self.game.board = chess.Board('4k3/8/8/8/8/8/8/R3K3 w - - 99 1')
        status = self.client.get('/api/state').json
        self.assertEqual(status['status'], 'playing')
        self.assertTrue(status['rules']['can_claim_fifty'])
        self.assertEqual(self.post('/api/claim_draw').json['status'], 'claimed_draw')

    def test_expired_clock_prevents_late_draw_and_abort(self):
        self.game.new(bot_enabled=False, time_control=30)
        with self.game.lock:
            self.game.board = chess.Board('r3k3/8/8/8/8/8/8/4K3 w - - 99 1')
            self.assertTrue(self.game.board.can_claim_fifty_moves())
            self.game.clocks['w'] = .01
            self.game.last_tick -= .15
            self.game.last_draw_offer = 'pending'
            self.game.draw_offered_by = 'b'
        self.assertEqual(self.post('/api/claim_draw').status_code, 400)
        result = self.client.get('/api/state').json
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['winner'], 'b')
        self.assertEqual(self.post('/api/agree_draw', color='w').status_code, 400)
        self.assertEqual(self.post('/api/offer_draw', color='w').status_code, 400)
        self.assertEqual(self.post('/api/abort').status_code, 400)

    def test_bot_draw_claim_only_on_human_turn(self):
        self.game.new(bot_enabled=True, you_color='w')
        with self.game.lock:
            self.game.board = chess.Board('4k3/8/8/8/8/8/8/R3K3 b - - 99 1')
        self.assertTrue(self.game.board.can_claim_fifty_moves())
        self.assertEqual(self.post('/api/claim_draw').status_code, 400)
        self.assertEqual(self.client.get('/api/state').json['status'], 'playing')
        with self.game.lock:
            self.game.board.turn = chess.WHITE
        self.assertEqual(self.post('/api/claim_draw').json['status'], 'claimed_draw')

    def test_draw_offer_requires_opponents_agreement(self):
        self.assertEqual(self.post('/api/agree_draw', color='b').status_code, 400)
        offer = self.post('/api/offer_draw', color='w')
        self.assertEqual(offer.json['draw_offer'], 'pending')
        self.assertEqual(self.post('/api/agree_draw', color='w').status_code, 400)
        self.assertEqual(self.post('/api/agree_draw', color='b').json['status'], 'agreed_draw')

    def test_draw_offer_survives_offerers_move_but_not_opponents(self):
        self.post('/api/offer_draw', color='w')
        self.assertEqual(self.post('/api/move', **{'from':'e2','to':'e4'}).json['draw_offer'],
                         'pending')
        self.post('/api/move', **{'from':'e7','to':'e5'})
        self.assertIsNone(self.client.get('/api/state').json['draw_offer'])

    def test_bot_cannot_be_forced_into_agreement(self):
        self.game.new(bot_enabled=True)
        self.assertEqual(self.post('/api/agree_draw', color='b').status_code, 400)
        self.assertEqual(self.post('/api/offer_draw').json['draw_offer'], 'declined')

    def test_undo_restores_clocks_increments_and_finished_result(self):
        self.game.new(bot_enabled=False, increment=2)
        with self.game.lock:
            before = dict(self.game.clocks)
            self.game.last_tick -= 5
        move = self.post('/api/move', **{'from':'e2','to':'e4'})
        self.assertLess(move.json['clocks']['w'], before['w'])
        with self.game.lock:
            self.game.clocks['b'] = .01
            self.game.last_tick -= .4
        self.assertEqual(self.client.get('/api/state').json['status'], 'timeout')
        undo = self.post('/api/undo')
        self.assertEqual(undo.json['status'], 'playing')
        self.assertEqual(undo.json['san'], [])
        self.assertAlmostEqual(undo.json['clocks']['w'], before['w'], delta=.1)
        stats = self.client.get('/api/stats').json
        self.assertEqual(stats['games'], 0)
        self.assertEqual(stats['moves']['user_game'], 0)

    def test_bot_undo_rewinds_a_turn_or_only_a_pending_human_move(self):
        self.game.new(bot_enabled=True, think_delay=5)
        with self.game.lock:
            for uci, actor in [('e2e4', 'user'), ('e7e5', 'bot'), ('g1f3', 'user')]:
                self.assertTrue(self.game._apply(chess.Move.from_uci(uci)))
                if actor == 'bot':
                    self.game.stats.record_bot_move(.25, 0.0, uci)
                else:
                    self.game.stats.record_user_move()
        self.assertEqual(self.post('/api/undo').json['san'], ['e4', 'e5'])
        stats = self.client.get('/api/stats').json
        self.assertEqual((stats['moves']['user_game'], stats['moves']['bot_game']), (1, 1))
        self.assertEqual(self.post('/api/undo').json['san'], [])
        stats = self.client.get('/api/stats').json
        self.assertEqual((stats['moves']['user_game'], stats['moves']['bot_game']), (0, 0))
        self.assertEqual(stats['reaction_game']['n'], 0)

    def test_promotion_to_queen_can_win_a_captured_rook(self):
        moves = ['a2a4', 'h7h5', 'a4a5', 'h5h4', 'a5a6', 'h4h3',
                 'a6b7', 'h3g2', 'b7a8q', 'g2h1q']
        for move in moves:
            response = self.post('/api/move', **{'from':move[:2], 'to':move[2:4],
                                                 'promotion':move[4:] or 'q'})
            self.assertEqual(response.status_code, 200, (move, response.json))
        state = self.client.get('/api/state').json
        self.assertIn('Qnbqkbnr', state['fen'])
        self.assertIn('RNBQKBNq', state['fen'])
        self.assertIn('bxa8=Q', state['san'])
        self.assertIn('gxh1=Q', state['san'])
        self.assertIn('gxh1=Q', state['pgn'])
        self.assertEqual(state['captured']['w'], ['r', 'p'])
        self.assertEqual(state['captured']['b'], ['R', 'P'])

    def test_castling_en_passant_underpromotion_are_legal(self):
        cases = [
            ('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1', 'e1', 'g1', 'q', 'O-O'),
            ('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1', 'e5', 'd6', 'q', 'exd6'),
            ('4k3/P7/8/8/8/8/8/4K3 w - - 0 1', 'a7', 'a8', 'n', 'a8=N'),
        ]
        for fen, frm, to, promo, san in cases:
            with self.subTest(san=san):
                self.game.new(bot_enabled=False)
                with self.game.lock:
                    self.game.board = chess.Board(fen)
                result = self.post('/api/move', **{'from':frm, 'to':to, 'promotion':promo})
                self.assertEqual(result.status_code, 200, result.json)
                self.assertEqual(result.json['san'][-1], san)
                if san == 'exd6':
                    self.assertEqual(result.json['captured']['w'], ['p'])
                elif san == 'a8=N':
                    self.assertEqual(result.json['captured'], {'w':[], 'b':[]})

    def test_both_search_failures_still_finish_the_bot_turn(self):
        def broken(*args, **kwargs):
            raise RuntimeError('simulated engine failure')
        self.game.bot.choose_move = broken
        self.game.fallback.choose_move = broken
        with patch.object(app.logger, 'exception') as logged:
            self.game.new(you_color='b', bot_enabled=True, think_delay=0)
            for _ in range(100):
                if not self.game.bot_pending and self.game.move_history:
                    break
                time.sleep(.01)
        state = self.client.get('/api/state').json
        self.assertEqual(len(state['san']), 1)
        self.assertFalse(state['bot_thinking'])
        self.assertGreaterEqual(logged.call_count, 2)

    def test_search_does_not_hold_game_lock_and_undo_discards_stale_result(self):
        began, release = threading.Event(), threading.Event()
        def slow_move(board, level, cancel=None):
            began.set()
            release.wait(2)
            return chess.Move.from_uci('e7e5')
        self.game.bot.choose_move = slow_move
        self.game.new(bot_enabled=True, think_delay=0)
        response = self.post('/api/move', **{'from':'e2','to':'e4'})
        self.assertTrue(response.json['bot_thinking'])
        self.assertTrue(began.wait(2))
        start = time.monotonic()
        self.assertEqual(self.client.get('/api/state').status_code, 200)
        undone = self.post('/api/undo')
        self.assertLess(time.monotonic() - start, .7)
        release.set()
        self.assertEqual(undone.json['san'], [])
        for _ in range(30):
            if not self.game.bot_pending:
                break
            time.sleep(.01)
        time.sleep(.04)
        self.assertEqual(self.client.get('/api/state').json['san'], [])


class SearchTests(unittest.TestCase):
    def test_quiescence_recognizes_mate_at_horizon(self):
        board = chess.Board('7k/6Q1/5K2/8/8/8/8/8 b - - 0 1')
        self.assertEqual(BaselineBot()._quiescence(board, -INF, INF, 0), -MATE)

    def test_search_finds_distinct_mates_and_hanging_queen(self):
        for lesson in (HOLDOUT[0], HOLDOUT[1], HOLDOUT[2]):
            with self.subTest(skill=lesson.skill):
                move = BaselineBot().choose_move(chess.Board(lesson.fen), 2)
                self.assertEqual(move.uci(), lesson.move)

    def test_search_keys_include_clock_and_repetition(self):
        normal, with_clock = chess.Board(), chess.Board()
        with_clock.halfmove_clock = 42
        self.assertNotEqual(position_key(normal), position_key(with_clock))
        repeated = chess.Board()
        for move in ['g1f3','g8f6','f3g1','f6g8'] * 2:
            repeated.push_uci(move)
        repeated.halfmove_clock = normal.halfmove_clock
        self.assertNotEqual(position_key(normal), position_key(repeated))
        twice, thrice = chess.Board(), chess.Board()
        cycle = ['g1f3','g8f6','f3g1','f6g8']
        for move in cycle:
            twice.push_uci(move)
        for move in cycle * 2:
            thrice.push_uci(move)
        twice.halfmove_clock = thrice.halfmove_clock
        self.assertNotEqual(_tt_key(twice), _tt_key(thrice))

    def test_unapproved_existing_model_is_not_the_default_bot(self):
        with patch.dict(os.environ, {'CHESS_ENGINE':'auto'}):
            bot = AIBot(checkpoint='checkpoints/model.npz')
        self.assertFalse(bot.has_checkpoint)
        self.assertEqual(bot.engine, 'baseline-search')


class TrainingTests(unittest.TestCase):
    def test_lessons_are_valid_and_holdout_is_disjoint(self):
        verify_lessons()
        self.assertGreaterEqual(len(HOLDOUT), 8)
        self.assertTrue({x.fen for x in TRAIN}.isdisjoint({x.fen for x in HOLDOUT}))
        synthetic = synthetic_lessons()
        augmented = {board.fen() for board, _, _, _ in examples(TRAIN + synthetic, augment=True)}
        self.assertTrue(augmented.isdisjoint({x.fen for x in HOLDOUT}))
        self.assertGreater(len(synthetic), 100)
        self.assertGreater(len(rows(TRAIN + synthetic, augment=True)[0]), len(synthetic))

    def test_arena_deadline_after_a_slow_move_is_unfinished(self):
        deadline = time.monotonic() + .001
        def slow_legal(board):
            time.sleep(.003)
            return next(iter(board.legal_moves))
        result = play_game(slow_legal, slow_legal, deadline=deadline)
        self.assertEqual(result.reason, 'time_limit')

    def test_illegal_move_loses_instead_of_becoming_draw(self):
        for bad in (None, 'e2e4', chess.Move.from_uci('a1a8')):
            with self.subTest(bad=bad):
                result = play_game(lambda board: bad, lambda board: bad)
                self.assertEqual(result.reason, 'illegal_move')
                self.assertIs(result.winner, chess.BLACK)

    def test_truncated_arena_games_are_not_scored_as_draws(self):
        result = evaluate_vs_baseline(object(), games=2, max_plies=0)
        self.assertEqual(result['unfinished'], 2)
        self.assertEqual(result['draw'], 0)
        self.assertEqual(result['game_scores'], [None, None])

    def test_paired_gate_skips_incomplete_pairs(self):
        delta, lower, count = paired_delta(
            {'game_scores':[1., None, 0., 1.]},
            {'game_scores':[.5, 1., 1., None]})
        self.assertEqual(count, 2)
        self.assertAlmostEqual(delta, -.25)
        self.assertLessEqual(lower, delta)

    def test_gate_bounds_do_not_claim_certainty_from_perfect_small_samples(self):
        from ai.evaluate import score_bounds
        # A perfect 12-game score is promising, not a proof of 100% strength.
        lower, upper = score_bounds([1.] * 12)
        self.assertLess(lower, 1.)
        self.assertEqual(upper, 1.)
        delta, delta_lower, count = paired_delta(
            {'game_scores':[1.] * 12}, {'game_scores':[0.] * 12})
        self.assertEqual((delta, count), (1., 12))
        self.assertLess(delta_lower, delta)
        self.assertGreater(delta_lower, 0.)

    def test_strict_step_fails_without_silent_success(self):
        command = [sys.executable, '-c', 'raise SystemExit(17)']
        self.assertEqual(run_step(command, strict=False), 17)
        with self.assertRaises(subprocess.CalledProcessError):
            run_step(command, strict=True)

    def test_trainers_reject_active_paths_wrong_formats_and_empty_work(self):
        parser = argparse.ArgumentParser()
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()):
            tmp = Path(tmp)
            link = tmp / 'candidate.npz'
            link.symlink_to(ACTIVE_NPZ)
            for name in [str(ACTIVE_NPZ), str(link), str(tmp / 'model.pt')]:
                with self.subTest(path=name), self.assertRaises(SystemExit):
                    candidate_output(parser, name, '.npz')
            output = tmp / 'new.npz'
            empty = subprocess.run([sys.executable, 'ai/train_tactics.py', '--positions', '0',
                                    '--mates', '0', '--out', str(output)], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(empty.returncode, 1)
            self.assertFalse(output.exists())
            approved = ACTIVE_NPZ.with_suffix('.approved.json')
            guard = subprocess.run([sys.executable, 'ai/train_cli.py', '--dry-run',
                                    '--report', str(approved)], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(guard.returncode, 2)
            resume = tmp / 'unrelated.pt'
            resume.write_bytes(b'not a model')
            mismatched = subprocess.run([sys.executable, 'ai/train_cli.py', '--dry-run',
                                          '--preset', 'basics', '--resume', str(resume)],
                                         cwd=ROOT, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
            self.assertEqual(mismatched.returncode, 2)

    def test_atomic_copy_and_approval_are_content_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate, active = root / 'candidate.npz', root / 'model.npz'
            candidate.write_bytes(b'new checkpoint')
            active.write_bytes(b'old checkpoint')
            atomic_copy(candidate, active)
            self.assertEqual(active.read_bytes(), b'new checkpoint')
            receipt = approve_checkpoint(active, {'paired_games':32}, 'demo')
            self.assertTrue(approved_checkpoint(str(active)))
            self.assertEqual(json.loads(receipt.read_text())['gate']['paired_games'], 32)
            active.write_bytes(b'tampered model')
            self.assertFalse(approved_checkpoint(str(active)))

    def test_failed_copy_leaves_active_checkpoint_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate, active = root / 'candidate', root / 'active'
            candidate.write_bytes(b'new checkpoint')
            active.write_bytes(b'known good')
            with patch('ai.train_cli.shutil.copy2', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    atomic_copy(candidate, active)
            self.assertEqual(active.read_bytes(), b'known good')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['active', 'candidate'])


if __name__ == '__main__':
    unittest.main()
