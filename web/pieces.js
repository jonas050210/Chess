/* Original faceless, Staunton-inspired pieces. Every image is a self-contained
   SVG: no fonts, downloaded art, CDNs, raster pixels or facial features. The
   ivory and forest-enamel finishes share the same strong outline and plinth. */
const PALETTES = {
  white: {
    body: '#f9f7e9', light: '#fffefa', shadow: '#d9e6d8', edge: '#29483e',
    accent: '#77a988', metal: '#e3b758', metalLight: '#ffe5a0',
  },
  black: {
    body: '#345d50', light: '#638a74', shadow: '#1e3c34', edge: '#172e2b',
    accent: '#8ad0ac', metal: '#e1b45e', metalLight: '#ffe1a0',
  },
};

// A common weighted pedestal makes all six roles feel like one set. Broad
// contours survive downscaling to 38–45px squares on narrow screens.
const base = p => `
  <path d="M31 70 H69 L75 78 H25 Z" fill="${p.shadow}"/>
  <path d="M24 79 H76 L80 85 L77 89 Q50 92 23 89 L20 85 Z" fill="url(#body)"/>
  <path d="M26 84 Q50 87 74 84" fill="none" stroke="${p.accent}" stroke-width="2"/>`;

function pawn(p) {
  return `
    <circle cx="50" cy="27" r="13" fill="url(#body)"/>
    <path d="M43 20 Q47 17 51 18" fill="none" stroke="${p.light}" stroke-width="2.4"/>
    <path d="M39 39 Q50 43 61 39 L64 45 Q50 49 36 45 Z" fill="${p.shadow}"/>
    <path d="M41 47 C42 56 37 64 33 72 H67 C63 64 58 56 59 47 Z" fill="url(#body)"/>
    <path d="M36 70 Q50 73 64 70" fill="none" stroke="${p.accent}" stroke-width="2.2"/>
    ${base(p)}`;
}

function rook(p) {
  return `
    <path d="M22 16 H35 V25 H42 V16 H58 V25 H65 V16 H78 L76 33 H24 Z" fill="url(#body)"/>
    <path d="M26 34 H74 L71 41 H29 Z" fill="${p.shadow}"/>
    <path d="M36 41 H64 L68 72 H32 Z" fill="url(#body)"/>
    <path d="M41 45 L39 66 M59 45 L61 66" fill="none" stroke="${p.accent}" stroke-width="2.1"/>
    <path d="M31 39 H69" fill="none" stroke="${p.edge}" stroke-width="2.3"/>
    ${base(p)}`;
}

function knight(p) {
  return `
    <path d="M44 12 L54 26 Q66 28 73 40 L78 49 L71 53 L72 62 L67 72 H32 L36 61 L25 59 Q20 57 19 52 L17 46 L26 42 L33 32 L41 27 Z" fill="url(#body)"/>
    <path d="M53 27 Q65 29 72 41 L66 40 L70 47 L64 47 L68 54 Q63 58 64 70 H55 Q59 49 49 33 Z" fill="${p.shadow}" stroke="none"/>
    <path d="M52 30 Q61 36 63 43 M47 39 Q53 49 50 62" fill="none" stroke="${p.accent}" stroke-width="2.6"/>
    <path d="M32 72 Q39 60 39 57" fill="none" stroke="${p.edge}" stroke-width="2.3"/>
    ${base(p)}`;
}

function bishop(p) {
  return `
    <circle cx="50" cy="12" r="5" fill="url(#metal)"/>
    <path d="M50 20 C61 31 66 40 65 48 Q64 57 57 62 L65 73 H35 L43 62 Q36 57 35 48 C34 40 39 31 50 20 Z" fill="url(#body)"/>
    <path d="M57 30 L43 53" fill="none" stroke="${p.edge}" stroke-width="6.5"/>
    <path d="M57 30 L43 53" fill="none" stroke="${p.metal}" stroke-width="2.3"/>
    <path d="M39 56 Q50 62 61 56" fill="none" stroke="${p.accent}" stroke-width="2.4"/>
    ${base(p)}`;
}

function queen(p) {
  return `
    <circle cx="21" cy="22" r="4" fill="url(#metal)"/>
    <circle cx="36" cy="15" r="4" fill="url(#metal)"/>
    <circle cx="50" cy="12" r="4" fill="url(#metal)"/>
    <circle cx="64" cy="15" r="4" fill="url(#metal)"/>
    <circle cx="79" cy="22" r="4" fill="url(#metal)"/>
    <path d="M22 28 L30 49 L38 23 L50 48 L62 23 L70 49 L78 28 L72 63 L66 73 H34 L28 63 Z" fill="url(#body)"/>
    <path d="M31 55 Q50 62 69 55 L67 63 Q50 68 33 63 Z" fill="${p.shadow}"/>
    <path d="M33 54 Q50 59 67 54" fill="none" stroke="${p.accent}" stroke-width="2.6"/>
    <path d="M50 62 L54 58 L50 54 L46 58 Z" fill="url(#metal)" stroke-width="1.5"/>
    ${base(p)}`;
}

function king(p) {
  return `
    <path d="M47 7 H53 V17 H62 V23 H53 V33 H47 V23 H38 V17 H47 Z" fill="url(#metal)"/>
    <path d="M29 35 L36 44 L50 36 L64 44 L71 35 L68 57 L65 73 H35 L32 57 Z" fill="url(#body)"/>
    <path d="M34 54 Q50 62 66 54 L65 63 Q50 68 35 63 Z" fill="${p.shadow}"/>
    <path d="M36 53 Q50 58 64 53" fill="none" stroke="${p.accent}" stroke-width="2.6"/>
    <path d="M50 62 L54 58 L50 54 L46 58 Z" fill="url(#metal)" stroke-width="1.5"/>
    ${base(p)}`;
}

const DRAW = {p: pawn, r: rook, n: knight, b: bishop, q: queen, k: king};
const cache = new Map();

export function pieceSvg(symbol) {
  if (!/^[prnbqkPRNBQK]$/.test(symbol)) throw new TypeError('Unknown chess piece');
  const p = PALETTES[symbol === symbol.toUpperCase() ? 'white' : 'black'];
  const role = symbol.toLowerCase();
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100" aria-hidden="true">
    <defs>
      <linearGradient id="body" x1="10%" y1="0%" x2="90%" y2="100%">
        <stop offset="0" stop-color="${p.light}"/>
        <stop offset=".5" stop-color="${p.body}"/>
        <stop offset="1" stop-color="${p.shadow}"/>
      </linearGradient>
      <linearGradient id="metal" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0" stop-color="${p.metalLight}"/>
        <stop offset="1" stop-color="${p.metal}"/>
      </linearGradient>
    </defs>
    <ellipse cx="50" cy="92" rx="32" ry="3" fill="${p.edge}" opacity=".16"/>
    <g stroke="${p.edge}" stroke-width="3.3" stroke-linejoin="round" stroke-linecap="round">
      ${DRAW[role](p)}
    </g>
  </svg>`;
}

export function pieceUri(symbol) {
  if (!cache.has(symbol)) cache.set(symbol, 'data:image/svg+xml;charset=utf-8,' +
                                   encodeURIComponent(pieceSvg(symbol)));
  return cache.get(symbol);
}

export const PIECE_NAMES = {p: 'pawn', n: 'knight', b: 'bishop', r: 'rook',
                            q: 'queen', k: 'king'};
