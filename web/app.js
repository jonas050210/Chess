import {pieceUri, PIECE_NAMES} from './pieces.js';
import {START_FEN, fenToBoard, squareIndex, viewToSquare, squareToView,
        colorOf, isPlaying, legalTargets, clockText, gameStatus,
        coachMessage, animationParts} from './logic.js';

const $ = id => document.getElementById(id);
const board = $('board');
const arrowLayer = $('arrowsSvg');
const toastBox = $('toast');
const promotion = $('promotion');
const files = 'abcdefgh';
const controls = ['btnNewTop', 'btnNewCard', 'btnHint', 'btnUndo', 'btnFlip',
                  'btnOffer', 'btnClaim', 'btnAccept', 'btnAbort', 'btnResign'];
let state = null;
let gameId = sessionStorage.getItem('chess-game-id');
let connected = false;
let flipped = false;
let selected = null;
let hintSquare = null;
let focusSquare = 'e2';
let marked = new Set();
let arrows = new Set();
let drag = null;
let rightStart = null;
let localClocks = {w:600, b:600};
let lastClockSync = performance.now();
let requestVersion = 0;
let polling = false;
let analyzing = false;
let moveSending = false;
let analysis = null;
let toastTimeout = null;
let resignArmed = false;
let ghost = null;
let animationGeneration = 0;

function notify(message) {
  toastBox.textContent = message;
  toastBox.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toastBox.hidden = true; }, 3500);
}

async function api(path, data) {
  const headers = {};
  if (gameId) headers['X-Game-ID'] = gameId;
  const options = data === undefined ? {} : {method:'POST',
    body:JSON.stringify(data)};
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, headers, credentials:'same-origin'});
  const serverId = response.headers.get('X-Game-ID');
  if (serverId && serverId !== gameId) {
    gameId = serverId;
    sessionStorage.setItem('chess-game-id', gameId);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Server error (${response.status})`);
  return payload;
}

function connection(isOnline) {
  connected = isOnline;
  const badge = $('connectionBadge');
  badge.classList.toggle('online', isOnline);
  badge.classList.toggle('offline', !isOnline);
  badge.lastChild.textContent = isOnline ? ' Ready to play' : ' Server offline';
  renderActions();
}

function localBoard() { return fenToBoard(state.fen); }
function pieceAt(square) { return localBoard()[squareIndex(square)]; }
function canPremove() {
  return connected && isPlaying(state) && state.bot_enabled &&
    state.turn !== state.you_color && state.bot_thinking && state.settings.premove;
}
function canSelect(piece) {
  if (!connected || !piece || !isPlaying(state) || moveSending) return false;
  const color = colorOf(piece);
  if (canPremove()) return color === state.you_color;
  return color === state.turn && (!state.bot_enabled || color === state.you_color);
}
function userTurn() {
  return connected && isPlaying(state) &&
    (!state.bot_enabled || state.turn === state.you_color);
}

function syncForm(first = false) {
  if (!state) return;
  const settings = state.settings || {};
  if (first) {
    $('side').value = state.you_color;
    $('time').value = String(state.time_control);
    $('increment').value = String(state.increment);
  }
  $('level').value = String(state.difficulty);
  $('botEnabled').checked = state.bot_enabled;
  $('boardTheme').value = ['duo', 'blue', 'sand'].includes(settings.theme) ? settings.theme : 'duo';
  $('thinkDelay').value = String(state.think_delay);
  $('coords').checked = settings.coords;
  $('anim').checked = settings.animation;
  $('autoQueen').checked = settings.auto_queen;
  $('premove').checked = settings.premove;
  $('arrows').checked = settings.arrows;
}

function applyState(next, {force = false, animate = true, first = false} = {}) {
  const previous = state;
  const changed = force || !previous || previous.fen !== next.fen ||
    previous.last_move !== next.last_move || previous.status !== next.status ||
    JSON.stringify(previous.settings) !== JSON.stringify(next.settings) ||
    previous.premove !== next.premove || previous.bot_enabled !== next.bot_enabled;
  const oldRects = new Map();
  if (animate && previous && previous.fen !== next.fen && next.last_move &&
      (next.san?.length || 0) > (previous.san?.length || 0)) {
    for (const [from] of animationParts(next.last_move)) {
      const el = board.querySelector(`[data-square="${from}"]`);
      if (el) oldRects.set(from, el.getBoundingClientRect());
    }
  }
  if (previous && previous.premove && !next.premove && previous.fen !== next.fen &&
      (next.san?.length || 0) === (previous.san?.length || 0) + 1) {
    notify('Your queued move was no longer legal.');
  }
  if (previous && (next.san?.length || 0) < (previous.san?.length || 0)) {
    marked.clear(); arrows.clear();
  }
  state = next;
  flipped = !!next.settings?.flip;
  document.documentElement.dataset.theme = next.settings?.theme || 'duo';
  localClocks = {...next.clocks};
  lastClockSync = performance.now();
  connection(true);
  if (changed) {
    if (previous && previous.fen !== next.fen) {
      selected = null;
      hintSquare = null;
      cancelDrag();
      analysis = null;
    }
    syncForm(first);
    renderBoard();
    renderPlayers();
    renderMoves();
    renderAnalysis();
  } else {
    renderClocks();
    renderPlayers();
  }
  renderStatus();
  renderActions();
  if (oldRects.size && next.settings?.animation &&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    animateMove(next.last_move, previous.fen, oldRects);
  }
}

function renderBoard() {
  if (!state) return;
  const position = localBoard();
  const wasFocused = board.contains(document.activeElement);
  if (wasFocused) focusSquare = document.activeElement.dataset.square || focusSquare;
  const legal = selected && !canPremove() ? new Set(legalTargets(state, selected)) : new Set();
  const last = state.last_move;
  const premove = state.premove;
  const fragment = document.createDocumentFragment();
  for (let row = 0; row < 8; row++) for (let col = 0; col < 8; col++) {
    const square = viewToSquare(row, col, flipped);
    const file = files.indexOf(square[0]), rank = Number(square[1]) - 1;
    const code = position[squareIndex(square)];
    const tile = document.createElement('button');
    tile.type = 'button';
    tile.dataset.square = square;
    tile.setAttribute('role', 'gridcell');
    tile.tabIndex = focusSquare === square ? 0 : -1;
    tile.className = 'square' + ((file + rank) % 2 === 0 ? ' dark' : ' light');
    if (last && (square === last.slice(0, 2) || square === last.slice(2, 4))) tile.classList.add('last');
    if (selected === square) tile.classList.add('selected');
    if (hintSquare === square) tile.classList.add('hint');
    if (marked.has(square)) tile.classList.add('marked');
    if (state.check_square === square) tile.classList.add('check');
    if (premove && premove.slice(0, 2) === square) tile.classList.add('premove-from');
    if (premove && premove.slice(2, 4) === square) tile.classList.add('premove-to');
    if (canSelect(code)) tile.classList.add('own');
    const name = code ? `${colorOf(code) === 'w' ? 'white' : 'black'} ${PIECE_NAMES[code.toLowerCase()]}` : 'empty';
    tile.setAttribute('aria-label', `${square}, ${name}${state.check_square === square ? ', in check' : ''}`);
    if (code) {
      const image = document.createElement('img');
      image.className = 'piece'; image.src = pieceUri(code);
      image.alt = ''; image.draggable = false;
      tile.append(image);
    }
    if (legal.has(square)) {
      const marker = document.createElement('span');
      const from = position[squareIndex(selected)];
      marker.className = code || (from?.toLowerCase() === 'p' && selected[0] !== square[0]) ?
        'capture-indicator' : 'legal-dot';
      marker.setAttribute('aria-hidden', 'true');
      tile.append(marker);
    }
    if (state.settings?.coords) {
      if (col === 0) {
        const coord = document.createElement('span');
        coord.className = 'coord rank'; coord.textContent = square[1];
        coord.setAttribute('aria-hidden', 'true'); tile.append(coord);
      }
      if (row === 7) {
        const coord = document.createElement('span');
        coord.className = 'coord file'; coord.textContent = square[0];
        coord.setAttribute('aria-hidden', 'true'); tile.append(coord);
      }
    }
    fragment.append(tile);
  }
  board.replaceChildren(fragment);
  if (wasFocused) board.querySelector(`[data-square="${focusSquare}"]`)?.focus({preventScroll:true});
  renderArrows();
}

function renderArrows() {
  arrowLayer.replaceChildren();
  if (!state?.settings?.arrows) return;
  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns, 'defs');
  const marker = document.createElementNS(ns, 'marker');
  for (const [key, value] of Object.entries({id:'arrow-head', markerWidth:'.28',
    markerHeight:'.28', refX:'.19', refY:'.14', orient:'auto', markerUnits:'userSpaceOnUse'})) {
    marker.setAttribute(key, value);
  }
  const tip = document.createElementNS(ns, 'path');
  tip.setAttribute('d', 'M0 0 L.28 .14 L0 .28 Z');
  tip.setAttribute('fill', '#2b9abb');
  marker.append(tip); defs.append(marker); arrowLayer.append(defs);
  for (const pair of arrows) {
    const start = squareToView(pair.slice(0, 2), flipped);
    const finish = squareToView(pair.slice(2, 4), flipped);
    const fromX = start.col + .5, fromY = start.row + .5;
    const dx = finish.col - start.col, dy = finish.row - start.row;
    const length = Math.hypot(dx, dy) || 1;
    const line = document.createElementNS(ns, 'line');
    for (const [key, value] of Object.entries({x1:fromX, y1:fromY,
      x2:finish.col + .5 - dx / length * .25,
      y2:finish.row + .5 - dy / length * .25,
      stroke:'#2b9abb', 'stroke-width':'.105', 'stroke-linecap':'round',
      'stroke-opacity':'.83', 'marker-end':'url(#arrow-head)'})) line.setAttribute(key, String(value));
    arrowLayer.append(line);
  }
}

function renderPlayers() {
  if (!state) return;
  const top = flipped ? 'w' : 'b';
  const bottom = flipped ? 'b' : 'w';
  for (const [position, color] of [['top', top], ['bottom', bottom]]) {
    const human = color === state.you_color;
    $(`${position}Name`).textContent = human ? 'You' : (state.bot_enabled ? 'Garden bot' : 'Friend');
    const avatar = $(`${position}Avatar`);
    avatar.textContent = human ? 'YOU' : (state.bot_enabled ? 'BOT' : '2P');
    avatar.classList.toggle('you-avatar', human);
    avatar.classList.toggle('opponent-avatar', !human);
    const captureArea = $(`${position}Captured`);
    captureArea.replaceChildren();
    const taken = state.captured?.[color] || [];
    if (!taken.length) {
      captureArea.textContent = 'No captures yet';
      captureArea.style.fontSize = '10px';
      captureArea.style.color = '#8b9d88';
    } else {
      captureArea.style.fontSize = '';
      for (const symbol of taken) {
        const image = document.createElement('img');
        image.src = pieceUri(symbol); image.alt = `${PIECE_NAMES[symbol.toLowerCase()]} captured`;
        captureArea.append(image);
      }
    }
  }
  renderClocks();
}

function renderClocks() {
  if (!state) return;
  for (const [position, color] of [['top', flipped ? 'w' : 'b'],
                                    ['bottom', flipped ? 'b' : 'w']]) {
    const element = $(`${position}Clock`);
    const remaining = localClocks[color] ?? 0;
    element.textContent = clockText(remaining);
    element.classList.toggle('active', isPlaying(state) && state.turn === color);
    element.classList.toggle('low', isPlaying(state) && state.turn === color && remaining < 20);
    element.setAttribute('aria-label', `${color === 'w' ? 'White' : 'Black'} clock ${element.textContent}`);
  }
}

function renderStatus() {
  if (!state) return;
  const label = connected ? gameStatus(state) : 'Server offline';
  $('statusTitle').textContent = label;
  $('statusSubtitle').textContent = !connected ? 'Run python server.py to play.' :
    state.premove ? `Queued: ${state.premove.toUpperCase()} · only plays if legal` :
    state.draw_offer === 'pending' && !state.bot_enabled ?
      `${state.draw_offered_by === 'w' ? 'White' : 'Black'} offered a draw · the other player can accept.` :
    isPlaying(state) ? `${state.bot_enabled ? 'Against the bot' : 'Two-player board'} · level ${state.difficulty} · take your time.` :
    'Another game is just one click away.';
  const tag = $('matchTag');
  tag.textContent = !connected ? 'OFFLINE' : !isPlaying(state) ? 'GAME FINISHED' :
    state.bot_thinking ? 'BOT IS THINKING' : `${state.turn === 'w' ? 'WHITE' : 'BLACK'} TO PLAY`;
  tag.classList.toggle('thinking', !!state.bot_thinking);
  tag.classList.toggle('finished', !isPlaying(state));
  const [title, description] = connected ? coachMessage(state) :
    ['Ready when you are.', 'Start the server with python server.py, then refresh this page.'];
  $('coachTitle').textContent = title; $('coachBody').textContent = description;
}

function renderMoves() {
  if (!state) return;
  const moves = state.san || [];
  const list = $('movesList');
  list.replaceChildren();
  $('moveCount').textContent = `${moves.length} ${moves.length === 1 ? 'move' : 'moves'}`;
  if (!moves.length) {
    const empty = document.createElement('span'); empty.className = 'empty-moves';
    empty.textContent = 'Your first move starts the story.'; list.append(empty);
    return;
  }
  for (let index = 0; index < moves.length; index += 2) {
    const row = document.createElement('div'); row.className = 'move-row';
    const number = document.createElement('span'); number.className = 'move-index';
    number.textContent = `${index / 2 + 1}.`; row.append(number);
    for (let turn = 0; turn < 2; turn++) {
      const san = document.createElement('span'); san.className = 'move-san';
      san.textContent = moves[index + turn] || '';
      if (index + turn === moves.length - 1) san.classList.add('last');
      row.append(san);
    }
    list.append(row);
  }
  list.scrollTop = list.scrollHeight;
}

function renderActions() {
  if (!state) return;
  for (const id of controls) $(id).disabled = !connected;
  if (!connected) return;
  const live = isPlaying(state);
  $('btnHint').disabled = !userTurn();
  $('btnUndo').disabled = !state.san?.length;
  $('btnOffer').disabled = !live;
  $('btnClaim').disabled = !live || (state.bot_enabled && state.turn !== state.you_color) ||
    !(state.rules?.can_claim_threefold || state.rules?.can_claim_fifty);
  $('btnAccept').disabled = !live || state.bot_enabled || state.draw_offer !== 'pending';
  $('btnAbort').disabled = (state.san?.length || 0) > 1;
  $('btnResign').disabled = !live;
  if (!resignArmed) $('btnResign').textContent = 'Resign';
}

function renderAnalysis() {
  if (!state) return;
  $('fenText').textContent = state.fen;
  const result = analysis?.result;
  const centipawns = result?.eval_white;
  $('evalFill').style.height = centipawns == null ? '50%' :
    `${Math.min(96, Math.max(4, 50 + 46 * Math.tanh(centipawns / 450)))}%`;
  const formatted = centipawns == null ? '—' : `${centipawns > 0 ? '+' : ''}${(centipawns / 100).toFixed(1)}`;
  $('evalValue').textContent = formatted;
  $('analysisEval').textContent = formatted;
  $('analysisState').textContent = !connected ? 'Start the server for analysis' :
    analysis?.thinking ? 'Looking at the position…' :
    result ? `Local search · depth ${analysis.depth}` : 'Local analysis unavailable for this position';
  const info = $('analysisInfo'); info.replaceChildren();
  const fields = [['Best move', result?.best_san || '—'], ['Positions checked', result?.nodes ?? '—'],
                  ['Phase', result?.phase || state.rules?.phase || '—'],
                  ['Legal moves', state.rules?.legal_count ?? '—']];
  for (const [label, value] of fields) {
    const row = document.createElement('div');
    const caption = document.createElement('span'); caption.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = String(value);
    row.append(caption, strong); info.append(row);
  }
  const tags = $('tacticTags'); tags.replaceChildren();
  for (const text of result?.tactics || []) {
    const tag = document.createElement('span'); tag.className = 'analysis-tag';
    tag.textContent = text; tags.append(tag);
  }
  $('pvLine').textContent = result?.pv?.length ? result.pv.join(' ') : '—';
  const rules = $('rulesInfo'); rules.replaceChildren();
  for (const [label, value] of [
    ['Castling', state.rules?.castling || '—'],
    ['En passant', state.rules?.ep_square || '—'],
    ['Threefold claim', state.rules?.can_claim_threefold ? 'Available' : 'Not yet'],
    ['50-move claim', state.rules?.can_claim_fifty ? 'Available' : 'Not yet'],
  ]) {
    const item = document.createElement('div');
    const caption = document.createElement('span'); caption.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = value;
    item.append(caption, strong); rules.append(item);
  }
}

function animateMove(uci, oldFen, rectangles) {
  const generation = ++animationGeneration;
  const oldPosition = fenToBoard(oldFen);
  for (const [from, to] of animationParts(uci)) {
    const start = rectangles.get(from);
    const finish = board.querySelector(`[data-square="${to}"]`)?.getBoundingClientRect();
    const piece = oldPosition[squareIndex(from)];
    if (!start || !finish || !piece) continue;
    const destination = board.querySelector(`[data-square="${to}"] .piece`);
    if (destination) destination.style.visibility = 'hidden';
    const flying = document.createElement('img');
    flying.className = 'flying-piece'; flying.src = pieceUri(piece); flying.alt = '';
    flying.style.left = `${start.left}px`; flying.style.top = `${start.top}px`;
    flying.style.width = `${start.width}px`; flying.style.height = `${start.height}px`;
    document.body.append(flying);
    const motion = flying.animate([
      {transform:'translate(0,0)'},
      {transform:`translate(${finish.left - start.left}px,${finish.top - start.top}px)`},
    ], {duration:240, easing:'cubic-bezier(.2,.8,.25,1)'});
    const cleanup = () => {
      flying.remove();
      if (generation === animationGeneration && destination) destination.style.visibility = '';
    };
    motion.onfinish = cleanup;
    motion.oncancel = cleanup;
  }
}

function cancelDrag() {
  if (drag?.from) board.querySelector(`[data-square="${drag.from}"]`)?.classList.remove('drag-origin');
  drag = null;
  ghost?.remove(); ghost = null;
}
function moveGhost(event) {
  if (ghost) { ghost.style.left = `${event.clientX}px`; ghost.style.top = `${event.clientY}px`; }
}

function promotionDialog(color, done) {
  promotion.replaceChildren();
  const title = document.createElement('strong'); title.textContent = 'Time for a promotion!';
  const subtitle = document.createElement('p'); subtitle.textContent = 'Choose who your pawn becomes.';
  const options = document.createElement('div'); options.className = 'promotion-options';
  for (const [symbol, name] of [['q', 'Queen'], ['r', 'Rook'], ['b', 'Bishop'], ['n', 'Knight']]) {
    const choice = document.createElement('button');
    choice.className = 'promotion-choice'; choice.type = 'button';
    const image = document.createElement('img'); image.src = pieceUri(color === 'w' ? symbol.toUpperCase() : symbol);
    image.alt = '';
    const text = document.createElement('span'); text.textContent = name;
    choice.append(image, text);
    choice.addEventListener('click', () => { promotion.hidden = true; done(symbol); });
    options.append(choice);
  }
  const close = document.createElement('button'); close.className = 'promotion-close';
  close.type = 'button'; close.textContent = 'Maybe later';
  close.addEventListener('click', () => { promotion.hidden = true; board.focus(); });
  promotion.append(title, subtitle, options, close);
  promotion.hidden = false;
  options.querySelector('button')?.focus();
}

async function sendMove(from, to, piece, queued) {
  if (moveSending) return;
  moveSending = true;
  const serial = ++requestVersion;
  try {
    const next = await api(queued ? '/api/premove' : '/api/move',
                           {from, to, promotion:piece});
    if (serial === requestVersion) applyState(next);
    if (queued) notify('Move queued! It only plays if legal after the bot moves.');
  } catch (error) {
    notify(error.message);
    await refreshState();
  } finally { moveSending = false; renderActions(); }
}

function attemptMove(from, to) {
  if (!state || from === to) return;
  const queued = canPremove();
  const code = pieceAt(from);
  if (!queued && !legalTargets(state, from).includes(to)) {
    notify('That move is not legal. Try another square.');
    return;
  }
  selected = null; hintSquare = null;
  renderBoard();
  const isPromotion = code?.toLowerCase() === 'p' &&
    (queued ? to[1] === (state.you_color === 'w' ? '8' : '1') :
              (state.legal || []).some(move => move.startsWith(from + to) && move.length === 5));
  if (isPromotion && !state.settings.auto_queen) {
    promotionDialog(colorOf(code), choice => sendMove(from, to, choice, queued));
  } else sendMove(from, to, 'q', queued);
}

function activateSquare(square, event) {
  if (!state || !connected || !isPlaying(state)) return;
  const code = pieceAt(square);
  if (selected && square !== selected && (canPremove() || legalTargets(state, selected).includes(square))) {
    const from = selected;
    attemptMove(from, square);
    return;
  }
  if (canSelect(code)) {
    selected = square;
    focusSquare = square;
    renderBoard();
    if (event?.pointerId != null) {
      drag = {from:square, x:event.clientX, y:event.clientY, moved:false};
    }
  } else {
    selected = null;
    renderBoard();
  }
}

board.addEventListener('pointerdown', event => {
  const tile = event.target.closest('.square');
  if (!tile) return;
  if (event.button === 2) { rightStart = tile.dataset.square; event.preventDefault(); return; }
  if (event.button !== 0) return;
  activateSquare(tile.dataset.square, event);
  if (drag) event.preventDefault();
});
board.addEventListener('pointermove', event => {
  if (!drag) return;
  if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 7) {
    drag.moved = true;
    ghost = document.createElement('img'); ghost.className = 'drag-ghost';
    ghost.src = pieceUri(pieceAt(drag.from)); ghost.alt = '';
    document.body.append(ghost);
    board.querySelector(`[data-square="${drag.from}"]`)?.classList.add('drag-origin');
  }
  moveGhost(event);
});
window.addEventListener('pointerup', event => {
  if (event.button === 2 && rightStart) {
    const start = rightStart; rightStart = null;
    if (!state?.settings?.arrows) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.square')?.dataset.square;
    if (!target) return;
    if (start === target) {
      marked.has(start) ? marked.delete(start) : marked.add(start);
      renderBoard();
    } else {
      const key = start + target;
      arrows.has(key) ? arrows.delete(key) : arrows.add(key);
      renderArrows();
    }
    return;
  }
  if (!drag) return;
  const {from, moved} = drag;
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.square')?.dataset.square;
  cancelDrag();
  if (moved && target && target !== from) attemptMove(from, target);
  else renderBoard();
});
window.addEventListener('pointercancel', cancelDrag);
board.addEventListener('contextmenu', event => event.preventDefault());
board.addEventListener('keydown', event => {
  const tile = event.target.closest('.square');
  if (!tile) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault(); activateSquare(tile.dataset.square); return;
  }
  const delta = {ArrowUp:[-1,0], ArrowDown:[1,0], ArrowLeft:[0,-1], ArrowRight:[0,1]}[event.key];
  if (!delta) return;
  event.preventDefault();
  const view = squareToView(tile.dataset.square, flipped);
  const next = viewToSquare(Math.max(0, Math.min(7, view.row + delta[0])),
                            Math.max(0, Math.min(7, view.col + delta[1])), flipped);
  focusSquare = next;
  board.querySelector(`[data-square="${next}"]`)?.focus();
});

function gamePayload() {
  return {you_color:$('side').value, difficulty:Number($('level').value),
          time_control:Number($('time').value), increment:Number($('increment').value),
          bot_enabled:$('botEnabled').checked,
          think_delay:Number($('thinkDelay').value),
          settings:{theme:$('boardTheme').value, coords:$('coords').checked,
                    animation:$('anim').checked, auto_queen:$('autoQueen').checked,
                    premove:$('premove').checked, arrows:$('arrows').checked,
                    highlight:'yellow', texture:false}};
}

async function action(path, body = {}) {
  if (!connected) return notify('Server offline. Start python server.py first.');
  const serial = ++requestVersion;
  try {
    const next = await api(path, body);
    if (serial === requestVersion) applyState(next, {force:true, animate:path === '/api/move'});
    return next;
  } catch (error) {
    notify(error.message);
    await refreshState();
    return null;
  }
}

async function newGame() {
  if (!connected) return;
  const next = await action('/api/new', gamePayload());
  if (next) {
    analysis = null; marked.clear(); arrows.clear();
    selected = null; hintSquare = null;
    renderBoard(); renderAnalysis();
    notify('Fresh board, fresh start. You’ve got this!');
  }
}

async function updateSettings() {
  if (!connected || !state) return;
  const payload = gamePayload();
  await action('/api/settings', {difficulty:payload.difficulty,
    bot_enabled:payload.bot_enabled, think_delay:payload.think_delay,
    settings:{...payload.settings, flip:flipped}});
}

async function hint() {
  if (!userTurn()) return;
  try {
    const requestFen = state.fen;
    const answer = await api('/api/hint', {});
    if (requestFen !== state.fen) return;
    selected = answer.uci.slice(0, 2);
    hintSquare = answer.uci.slice(2, 4);
    renderBoard(); notify(`A little nudge: ${answer.san}`);
    setTimeout(() => {
      if (requestFen !== state?.fen || hintSquare !== answer.uci.slice(2, 4)) return;
      selected = hintSquare = null; renderBoard();
    }, 2500);
  } catch (error) { notify(error.message); }
}

async function copyText(text, label) {
  if (!text) return notify('Nothing to copy yet.');
  try {
    await navigator.clipboard.writeText(text);
    notify(`${label} copied to clipboard.`);
  } catch (_) {
    const input = document.createElement('textarea');
    input.value = text; input.style.position = 'fixed'; input.style.opacity = '0';
    document.body.append(input); input.select();
    const copied = document.execCommand('copy'); input.remove();
    notify(copied ? `${label} copied to clipboard.` : 'Clipboard unavailable on this browser.');
  }
}

function downloadPGN() {
  if (!state?.san?.length) return notify('Make a move before saving a game.');
  const result = !isPlaying(state) ? (state.winner === 'w' ? '1-0' :
    state.winner === 'b' ? '0-1' : '1/2-1/2') : '*';
  const content = `[Event "Chess Garden"]\n[Site "Local browser"]\n[Result "${result}"]\n\n${state.pgn} ${result}\n`;
  const url = URL.createObjectURL(new Blob([content], {type:'application/x-chess-pgn'}));
  const link = document.createElement('a'); link.href = url; link.download = 'chess-garden.pgn';
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  notify('Game saved as PGN.');
}

$('btnNewTop').addEventListener('click', newGame);
$('btnNewCard').addEventListener('click', newGame);
$('btnUndo').addEventListener('click', () => action('/api/undo'));
$('btnHint').addEventListener('click', hint);
$('btnFlip').addEventListener('click', () => {
  if (!connected) return;
  flipped = !flipped; renderBoard(); renderPlayers();
  action('/api/settings', {settings:{flip:flipped}});
});
$('btnOffer').addEventListener('click', async () => {
  const next = await action('/api/offer_draw');
  if (next) notify(next.draw_offer === 'accepted' ? 'Draw agreed.' :
                   next.draw_offer === 'declined' ? 'Bot declined the draw.' : 'Draw offered to your friend.');
});
$('btnClaim').addEventListener('click', () => action('/api/claim_draw'));
$('btnAccept').addEventListener('click', () => {
  if (state?.bot_enabled || state?.draw_offer !== 'pending') return;
  action('/api/agree_draw', {color:state.draw_offered_by === 'w' ? 'b' : 'w'});
});
$('btnAbort').addEventListener('click', async () => {
  const next = await action('/api/abort');
  if (next) notify('Game aborted. Ready for a new one!');
});
$('btnResign').addEventListener('click', () => {
  if (!resignArmed) {
    resignArmed = true; $('btnResign').textContent = 'Confirm resign?';
    setTimeout(() => { resignArmed = false; renderActions(); }, 3500);
  } else {
    resignArmed = false;
    action('/api/resign');
  }
});
$('btnCopyFEN').addEventListener('click', () => copyText(state?.fen, 'FEN'));
$('btnDownloadPGN').addEventListener('click', downloadPGN);
for (const id of ['level', 'botEnabled', 'thinkDelay', 'boardTheme', 'coords',
                  'anim', 'autoQueen', 'premove', 'arrows']) {
  $(id).addEventListener('change', () => {
    if (id === 'boardTheme') document.documentElement.dataset.theme = $('boardTheme').value;
    if (id === 'coords' && state) {
      state.settings.coords = $('coords').checked; renderBoard();
    }
    updateSettings();
  });
}

window.addEventListener('keydown', event => {
  if (event.target.closest('input,select,textarea,summary') || event.altKey ||
      event.ctrlKey || event.metaKey) return;
  if (event.key === 'Escape') {
    if (!promotion.hidden) { promotion.hidden = true; return; }
    selected = hintSquare = null; marked.clear(); arrows.clear(); renderBoard();
    if (state?.premove) action('/api/premove', {cancel:true});
    return;
  }
  if (!promotion.hidden || event.target.closest('.square')) return;
  const key = event.key.toLowerCase();
  if (key === 'n') newGame();
  if (key === 'u' && !$('btnUndo').disabled) action('/api/undo');
  if (key === 'h' && !$('btnHint').disabled) hint();
  if (key === 'f') $('btnFlip').click();
  if (key === 'o' && !$('btnOffer').disabled) $('btnOffer').click();
  if (key === 'a' && !$('btnAbort').disabled) $('btnAbort').click();
  if (key === 'c') { marked.clear(); arrows.clear(); renderBoard(); }
});

setInterval(() => {
  if (!state || !connected) return;
  const now = performance.now(), elapsed = Math.max(0, (now - lastClockSync) / 1000);
  lastClockSync = now;
  if (isPlaying(state) && state.clock_started) {
    localClocks[state.turn] = Math.max(0, (localClocks[state.turn] || 0) - elapsed);
    renderClocks();
  }
}, 200);

async function refreshState() {
  if (polling) return;
  polling = true;
  const serial = requestVersion;
  try {
    const next = await api('/api/state');
    if (serial === requestVersion) applyState(next, {first:!connected});
  } catch (_) {
    connection(false);
    if (!state) { state = offlineBoard(); renderBoard(); renderPlayers(); renderMoves(); renderStatus(); renderAnalysis(); }
    else renderStatus();
  } finally { polling = false; }
}

async function refreshAnalysis() {
  if (!connected || !state || analyzing) return;
  analyzing = true;
  try {
    const answer = await api('/api/analysis');
    if (answer.fen === state.fen) { analysis = answer; renderAnalysis(); }
  } catch (_) { /* State polling reports connection errors. */ }
  finally { analyzing = false; }
}

function offlineBoard() {
  return {fen:START_FEN, turn:'w', legal:[], san:[], pgn:'', last_move:null,
    status:'playing', check:false, captured:{w:[], b:[]}, clocks:{w:600, b:600},
    you_color:'w', difficulty:3, bot_enabled:true, bot_thinking:false,
    clock_started:false, time_control:600, increment:0, think_delay:.6,
    settings:{theme:'duo',coords:true,animation:true,auto_queen:false,premove:true,arrows:true,flip:false},
    rules:{legal_count:20}};
}

refreshState();
setInterval(refreshState, 650);
setInterval(refreshAnalysis, 1500);
