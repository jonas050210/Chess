import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {START_FEN, fenToBoard, squareIndex, viewToSquare, squareToView,
        legalTargets, animationParts, clockText, gameStatus, coachMessage} from '../web/logic.js';
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
               'Bot is thinking… you can queue a move.');
  assert.equal(gameStatus({...position, bot_enabled:false, status:'check',
                           check:true, turn:'b'}), 'Black is in check!');
  assert.equal(coachMessage({...position, rules:{can_claim_threefold:true}, san:[]})[0],
               'A draw is yours to claim.');
  assert.equal(clockText(19.58), '0:19.5');
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

test('web entry point is browser-only and self-hosted', () => {
  const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('/static/app.js'));
  assert.ok(html.includes('/static/styles.css'));
  assert.ok(!html.includes('main.py'));
  assert.ok(!html.includes('https://'));
  assert.ok(!html.includes('<script>'));
});
