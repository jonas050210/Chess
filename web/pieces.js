/* Original, infinitely scalable chess illustrations. No PNGs, icon fonts or CDNs.
   Every role has its own Staunton-inspired silhouette; both sides have strong
   outlines and different body fills so they read on either board color. */
const PALETTES = {
  white: {body: '#fffcf2', shade: '#e3ecd7', edge: '#243d37', detail: '#72b66d',
          jewel: '#f3bc46', glint: '#ffffff', eye: '#243d37'},
  black: {body: '#34564b', shade: '#203c35', edge: '#172c2a', detail: '#7fe2b4',
          jewel: '#f4c76c', glint: '#638b77', eye: '#fff5d4'},
};

const base = (p) => `
  <path d="M31 72 Q50 69 69 72 L74 79 H26 Z" fill="${p.shade}"/>
  <path d="M25 79 Q50 75 75 79 L79 85 Q79 90 73 90 H27 Q21 90 21 85 Z" fill="${p.body}"/>
  <path d="M31 82 Q50 79 69 82" fill="none" stroke="${p.detail}" stroke-width="2"/>`;

function pawn(p) {
  return `
    <circle cx="50" cy="28" r="13" fill="${p.body}"/>
    <path d="M42 42 Q32 46 35 56 Q37 62 42 64 L35 72 H65 L58 64 Q63 60 65 55 Q68 46 58 42 Z" fill="${p.body}"/>
    <path d="M40 46 Q35 53 42 60" fill="none" stroke="${p.detail}" stroke-width="2.6"/>
    <path d="M39 64 Q50 69 61 64" fill="none" stroke="${p.edge}" stroke-width="2.5"/>
    <circle cx="45" cy="27" r="1.45" fill="${p.eye}" stroke="none"/>
    <circle cx="55" cy="27" r="1.45" fill="${p.eye}" stroke="none"/>
    <path d="M46 33 Q50 36 54 33" fill="none" stroke="${p.eye}" stroke-width="1.5"/>
    ${base(p)}`;
}

function rook(p) {
  return `
    <path d="M24 16 H36 V24 H43 V16 H57 V24 H64 V16 H76 V31 L70 38 H30 L24 31 Z" fill="${p.body}"/>
    <path d="M33 38 H67 L64 60 L69 72 H31 L36 60 Z" fill="${p.body}"/>
    <path d="M32 36 H68" fill="none" stroke="${p.detail}" stroke-width="3"/>
    <path d="M38 46 V60 M50 45 V62 M62 46 V60" fill="none" stroke="${p.detail}" stroke-width="2.4"/>
    <path d="M46 24 V31 H54 V24" fill="${p.shade}"/>
    ${base(p)}`;
}

function knight(p) {
  return `
    <path d="M40 72 Q43 59 39 53 L27 55 Q21 55 19 51 L17 44 L24 33 L33 28 L35 19 L45 12 L50 23 Q69 23 76 39 L80 48 Q80 52 75 55 L66 53 Q65 63 68 72 Z" fill="${p.body}"/>
    <path d="M50 23 Q63 28 68 38 L63 41 L69 46 L63 52 Q60 60 62 70" fill="none" stroke="${p.detail}" stroke-width="3.2"/>
    <path d="M24 44 Q30 46 35 41" fill="none" stroke="${p.edge}" stroke-width="2"/>
    <circle cx="41" cy="34" r="2.5" fill="${p.eye}" stroke="none"/>
    <path d="M37 26 L44 18" fill="none" stroke="${p.edge}" stroke-width="2.5"/>
    ${base(p)}`;
}

function bishop(p) {
  return `
    <circle cx="50" cy="13" r="5" fill="${p.jewel}"/>
    <path d="M50 20 Q65 31 65 44 Q65 54 55 60 L64 72 H36 L45 60 Q35 54 35 44 Q35 31 50 20 Z" fill="${p.body}"/>
    <path d="M56 27 L42 50" fill="none" stroke="${p.edge}" stroke-width="5"/>
    <path d="M56 27 L42 50" fill="none" stroke="${p.jewel}" stroke-width="2.1"/>
    <path d="M38 53 Q50 63 62 53" fill="none" stroke="${p.detail}" stroke-width="2.8"/>
    <path d="M42 62 H58" fill="none" stroke="${p.edge}" stroke-width="2"/>
    ${base(p)}`;
}

function queen(p) {
  return `
    <circle cx="22" cy="22" r="4" fill="${p.jewel}"/>
    <circle cx="39" cy="14" r="4" fill="${p.jewel}"/>
    <circle cx="61" cy="14" r="4" fill="${p.jewel}"/>
    <circle cx="78" cy="22" r="4" fill="${p.jewel}"/>
    <path d="M23 27 L33 43 L39 20 L50 41 L61 20 L67 43 L77 27 L70 58 L65 72 H35 L30 58 Z" fill="${p.body}"/>
    <path d="M32 52 Q50 60 68 52 L65 61 Q50 65 35 61 Z" fill="${p.shade}"/>
    <path d="M34 51 Q50 57 66 51" fill="none" stroke="${p.detail}" stroke-width="2.3"/>
    <path d="M50 45 L54 49 L50 53 L46 49 Z" fill="${p.jewel}" stroke-width="1.5"/>
    ${base(p)}`;
}

function king(p) {
  return `
    <path d="M47 7 H53 V16 H62 V22 H53 V32 H47 V22 H38 V16 H47 Z" fill="${p.jewel}"/>
    <path d="M29 35 L35 42 L50 35 L65 42 L71 35 L68 56 L64 72 H36 L32 56 Z" fill="${p.body}"/>
    <path d="M34 53 Q50 59 66 53 L64 62 Q50 66 36 62 Z" fill="${p.shade}"/>
    <path d="M36 51 Q50 56 64 51" fill="none" stroke="${p.detail}" stroke-width="2.8"/>
    <path d="M46 43 L50 39 L54 43 L50 47 Z" fill="${p.jewel}" stroke-width="1.3"/>
    ${base(p)}`;
}

const DRAW = {p: pawn, r: rook, n: knight, b: bishop, q: queen, k: king};
const cache = new Map();

export function pieceSvg(symbol) {
  if (!/^[prnbqkPRNBQK]$/.test(symbol)) throw new TypeError('Unknown chess piece');
  const palette = PALETTES[symbol === symbol.toUpperCase() ? 'white' : 'black'];
  const role = symbol.toLowerCase();
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100" aria-hidden="true">
    <ellipse cx="50" cy="91" rx="32" ry="3" fill="${palette.edge}" opacity=".15"/>
    <g stroke="${palette.edge}" stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round">
      ${DRAW[role](palette)}
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
