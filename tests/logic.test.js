import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {START_FEN, fenToBoard, squareIndex, viewToSquare, squareToView,
        legalTargets, animationParts, clockText, moveTimeText,
        gameStatus, coachMessage} from '../web/logic.js';
import {pieceSvg, pieceUri} from '../web/pieces.js';

test('a full starting board is read without losing piece colors', () => {
  const board = fenToBoard(START_FEN);
  assert.equal(board.length, 64);
  assert.equal(board[squareIndex('a8')], 'r');
  assert.equal(board[squareIndex('e1')], 'K');
  assert.equal(board[squareIndex('e4')], null);
  assert.throws(() => fenToBoard('7/8/8/8/8/8/8/8 w'), /Invalid/);
});

test('flipped squares and coordinates retain the proper orientation', () => {
  assert.equal(viewToSquare(0, 0), 'a8');
  assert.equal(viewToSquare(7, 0), 'a1');
  assert.equal(viewToSquare(0, 0, true), 'h1');
  assert.equal(viewToSquare(7, 7, true), 'a8');
  for (const square of ['a8', 'e2', 'g7', 'h1']) for (const flipped of [true, false]) {
    const {row, col} = squareToView(square, flipped);
    assert.equal(viewToSquare(row, col, flipped), square);
  }
});

test('castling animation moves both king and rook', () => {
  assert.deepEqual(animationParts('e1g1'), [['e1','g1'],['h1','f1']]);
  assert.deepEqual(animationParts('e8c8'), [['e8','c8'],['a8','d8']]);
  assert.deepEqual(animationParts('e5d6'), [['e5','d6']]);
});

test('legal markers and status are driven by server state', () => {
  const position = {legal:['e2e3','e2e4','g1f3'], status:'playing',
    turn:'w', you_color:'w', bot_enabled:true, bot_thinking:false};
  assert.deepEqual(legalTargets(position, 'e2'), ['e3', 'e4']);
  assert.equal(gameStatus(position), 'Your move');
  assert.equal(gameStatus({...position, turn:'b', bot_thinking:true}),
               'Bot is thinking… wait for your turn.');
  assert.equal(gameStatus({...position, bot_enabled:false, status:'check',
                           check:true, turn:'b'}), 'Black is in check!');
  assert.equal(coachMessage({...position, rules:{can_claim_threefold:true}, san:[]})[0],
               'A draw is yours to claim.');
  assert.equal(clockText(19.58), '0:19.5');
  assert.equal(clockText(3661), '1:01:01');
  assert.equal(moveTimeText(812), '0.812 s (812 ms)');
  assert.equal(moveTimeText(2345), '2.35 s (2345 ms)');
});

test('the twelve pieces are distinct self-contained vector images', () => {
  const symbols = 'KQRBNPkqrbnp';
  const images = [...symbols].map(pieceSvg);
  assert.equal(new Set(images).size, 12);
  for (const symbol of symbols) {
    const image = pieceSvg(symbol);
    assert.match(image, /viewBox="0 0 100 100"/);
    assert.match(pieceUri(symbol), /^data:image\/svg\+xml/);
    assert.ok(!image.includes('<image '), 'piece must remain vector');
  }
  assert.throws(() => pieceSvg('x'), TypeError);
});

test('board figures and decorative pawns have no drawn eyes or faces', () => {
  for (const symbol of ['P', 'p']) {
    // A pawn has one circle for its round head, never two tiny eye dots.
    assert.equal((pieceSvg(symbol).match(/<circle\b/g) || []).length, 1);
  }
  for (const symbol of ['N', 'n']) {
    // The horse has a recognizable silhouette and mane, but no facial marks.
    assert.equal((pieceSvg(symbol).match(/<circle\b/g) || []).length, 0);
  }
  const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
  for (const element of ['brand-mark', 'coach-icon']) {
    const illustration = html.match(new RegExp(`class="${element}"[\\s\\S]*?<\\/svg>`))?.[0];
    assert.ok(illustration, `missing ${element} illustration`);
    assert.equal((illustration.match(/<circle\b/g) || []).length, 2,
                 `${element}: background and head only, no eye dots`);
  }
});

test('web entry point is browser-only and self-hosted', () => {
  const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('/static/app.js'));
  assert.ok(html.includes('/static/styles.css'));
  assert.ok(!html.includes('main.py'));
  assert.ok(!html.includes('https://'));
  assert.ok(!html.includes('<script>'));
});
