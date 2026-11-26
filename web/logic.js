/* Pure board/UI helpers. Tested with Node; the server remains rule-authoritative. */
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export function fenToBoard(fen) {
  const rows = fen.split(' ')[0].split('/');
  if (rows.length !== 8) throw new Error('Invalid board');
  const result = [];
  for (const row of rows) {
    let count = 0;
    for (const char of row) {
      if (/^[1-8]$/.test(char)) {
        result.push(...Array(Number(char)).fill(null));
        count += Number(char);
      } else if (/^[prnbqkPRNBQK]$/.test(char)) {
        result.push(char);
        count++;
      } else throw new Error('Invalid piece in FEN');
    }
    if (count !== 8) throw new Error('Invalid board row');
  }
  return result;
}

export function squareIndex(square) {
  if (!/^[a-h][1-8]$/.test(square)) throw new Error('Invalid square');
  return (8 - Number(square[1])) * 8 + 'abcdefgh'.indexOf(square[0]);
}

export function viewToSquare(row, col, flipped = false) {
  const file = flipped ? 7 - col : col;
  const rank = flipped ? row + 1 : 8 - row;
  return 'abcdefgh'[file] + rank;
}

export function squareToView(square, flipped = false) {
  const file = 'abcdefgh'.indexOf(square[0]);
  const rank = Number(square[1]) - 1;
  return {row: flipped ? rank : 7 - rank, col: flipped ? 7 - file : file};
}

export const colorOf = piece => piece === piece.toUpperCase() ? 'w' : 'b';
export const isPlaying = state => state && (state.status === 'playing' || state.status === 'check');
export const legalTargets = (state, from) => (state?.legal || [])
  .filter(move => move.slice(0, 2) === from).map(move => move.slice(2, 4));

export function clockText(seconds) {
  const value = Math.max(0, seconds || 0);
  const minutes = Math.floor(value / 60);
  const whole = Math.floor(value % 60);
  if (value < 20) return `${minutes}:${String(whole).padStart(2, '0')}.${Math.floor((value % 1) * 10)}`;
  return `${minutes}:${String(whole).padStart(2, '0')}`;
}

const STATUS = {
  checkmate: 'Checkmate', stalemate: 'Stalemate', insufficient_material: 'Draw · no mating material',
  seventyfive_moves: 'Draw · 75 moves', fivefold_repetition: 'Draw · fivefold repetition',
  timeout: 'Time is up', resignation: 'Resignation', agreed_draw: 'Draw agreed',
  claimed_draw: 'Draw claimed', variant_win: 'Game over',
};

export function gameStatus(state) {
  if (!state) return 'Connecting…';
  if (isPlaying(state)) {
    if (state.check) {
      if (!state.bot_enabled) return `${state.turn === 'w' ? 'White' : 'Black'} is in check!`;
      return state.turn === state.you_color ? 'You are in check!' :
             'Check! Your opponent must respond.';
    }
    if (state.bot_thinking) return 'Bot is thinking… you can queue a move.';
    if (!state.bot_enabled) return `${state.turn === 'w' ? 'White' : 'Black'} to move`;
    return state.turn === state.you_color ? 'Your move' : 'Opponent to move';
  }
  const title = STATUS[state.status] || 'Game over';
  if (!state.winner) return title;
  return `${title} · ${state.winner === state.you_color ? 'you win!' : 'opponent wins'}`;
}

export function coachMessage(state) {
  if (!state) return ['One move at a time.', 'Start the server to play a game.'];
  if (!isPlaying(state)) {
    return [state.winner === state.you_color ? 'You did it!' : 'Another game, another lesson.',
            'Ready to try again? Every game makes you sharper.'];
  }
  if (state.check) return ['First things first: your king.',
                            'You must get out of check. Look for a safe square, a block or a capture.'];
  if (state.premove) return ['Move queued!', 'It will only play if it is legal after the bot moves.'];
  if (state.bot_thinking) return ['Look one move ahead.',
                                 'While the bot thinks, notice which of your pieces are defended.'];
  if ((state.rules?.can_claim_threefold || state.rules?.can_claim_fifty) &&
      (!state.bot_enabled || state.turn === state.you_color))
    return ['A draw is yours to claim.', 'Use “Claim draw” if you want to end the game.'];
  const ply = state.san?.length || 0;
  if (ply < 2) return ['Every adventure starts somewhere.',
                       'Try a central pawn move, like e4 or d4, to open the board.'];
  if (ply < 10) return ['Bring your team into the game.',
                        'Develop knights and bishops, then castle to keep your king safe.'];
  return ['Look before you leap.', 'Check for checks, captures and threats on every turn.'];
}

export function animationParts(uci) {
  if (!uci) return [];
  const from = uci.slice(0, 2), to = uci.slice(2, 4);
  const parts = [[from, to]];
  if (from[0] === 'e' && ['1', '8'].includes(from[1]) &&
      ['g', 'c'].includes(to[0]) && from[1] === to[1]) {
    const rank = from[1];
    parts.push(to[0] === 'g' ? [`h${rank}`, `f${rank}`] : [`a${rank}`, `d${rank}`]);
  }
  return parts;
}
