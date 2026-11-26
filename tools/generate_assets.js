/* Erzeugt alle Storybook-/Theme-Piece-SVGs aus den eingebetteten Vektoren in web/index.html.
   Usage: node tools/generate_assets.js <tempDir>
   Schreibt <tempDir>/svg/<theme>_<textured|flat>/*.svg und <tempDir>/pieces.svg.
   Keine persistente SVG-Sammlung mehr im Workspace. */
const fs = require('fs');
const path = require('path');
const outRoot = process.argv[2] || '.preview-tmp';
const svgRoot = path.join(outRoot, 'svg');
fs.mkdirSync(svgRoot, {recursive: true});

const h = fs.readFileSync('web/index.html', 'utf8');
const themeBlock = h.match(/const THEME_PIECE=\{[\s\S]*?\n\};/)[0];
const artBlock = h.slice(h.indexOf('const PIECE_PATHS='), h.indexOf('const PALETTES='));
const colorFn = h.match(/function pieceColor\(code\)\{[^\n]*\}/)[0];
const svgFn = h.match(/function pieceSVG\(code\)\{[\s\S]*?\n\}\nfunction svgURI/)[0].replace(/\nfunction svgURI$/, '');

let theme = 'duo';
let textureOn = true;
let svgId = 0;
eval(themeBlock + '\n' + artBlock + '\n' + colorFn + '\n' + svgFn);

const codes = ['K','Q','R','B','N','P','k','q','r','b','n','p'];
const themes = ['duo','green','brown','blue','midnight','sand'];
const variants = [true, false];
for (const t of themes) {
  for (const tx of variants) {
    theme = t; textureOn = tx;
    const variant = `${t}_${tx ? 'textured' : 'flat'}`;
    const dir = path.join(svgRoot, variant);
    fs.mkdirSync(dir, {recursive: true});
    for (const c of codes) {
      const name = (c === c.toUpperCase() ? 'w' : 'b') + c.toUpperCase() + '.svg';
      fs.writeFileSync(path.join(dir, name), pieceSVG(c));
    }
  }
}

/* Kombinierte Vorschau: 12 Storybook-Sticker auf weißem Papier. */
const cellW = 112, cellH = 132, cols = 6, rows = 2;
let out = `<svg xmlns="http://www.w3.org/2000/svg" width="${cols*cellW}" height="${rows*cellH}" viewBox="0 0 ${cols*cellW} ${rows*cellH}">`;
out += `<rect width="100%" height="100%" fill="#ffffff"/>`;
out += `<text x="14" y="24" font-family="DejaVu Sans, Segoe UI, sans-serif" font-size="15" font-weight="700" fill="#58cc02">NEUE STICKER-FIGUREN</text>`;
codes.forEach((c, i) => {
  const name = (c === c.toUpperCase() ? 'w' : 'b') + c.toUpperCase() + '.svg';
  const svg = fs.readFileSync(path.join(svgRoot, 'duo_textured', name), 'utf8');
  const b64 = Buffer.from(svg, 'utf8').toString('base64');
  const col = i % cols, row = Math.floor(i / cols);
  const x = col * cellW, y = row * cellH + 30;
  out += `<rect x="${x+6}" y="${y}" width="${cellW-12}" height="${cellH-34}" rx="16" fill="#f7f7f7" stroke="#afafaf" stroke-width="2"/>`;
  out += `<image href="data:image/svg+xml;base64,${b64}" x="${x+24}" y="${y+4}" width="64" height="64"/>`;
  out += `<text x="${x+cellW/2}" y="${y+84}" text-anchor="middle" font-family="DejaVu Sans, Segoe UI, sans-serif" font-size="11" font-weight="700" fill="#4b4b4b">${name.replace('.svg','')}</text>`;
});
out += `</svg>`;
fs.writeFileSync(path.join(outRoot, 'pieces.svg'), out);
console.log('svg_variants', themes.length * variants.length, 'files', themes.length * variants.length * codes.length + 1);
