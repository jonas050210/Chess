import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test.beforeEach(async ({page}) => {
  await page.goto('/');
  await expect(page.locator('#connectionBadge')).toHaveClass(/online/);
  await expect(page.locator('.square')).toHaveCount(64);
});

test('self-hosted SVG pieces render sharply and the board fits the screen', async ({page}) => {
  await expect(page.locator('.square .piece')).toHaveCount(32);
  const images = await page.locator('.square .piece').evaluateAll(pieces =>
    pieces.map(image => ({width:image.naturalWidth, src:image.src})));
  expect(images.every(image => image.width === 100 && image.src.startsWith('data:image/svg+xml'))).toBeTruthy();
  const board = await page.locator('#board').boundingBox();
  expect(Math.abs(board.width - board.height)).toBeLessThan(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test('unlimited time and the left stopwatch remain visible in fullscreen', async ({page}) => {
  await expect(page.locator('#level, #time, #increment, #premove')).toHaveCount(0);
  await expect(page.locator('#botTimeLabel')).toHaveText('Bot · Black');
  await expect(page.locator('#gameTime')).toContainText(':');
  await expect(page.locator('#yourTime')).toContainText(':');
  await page.locator('#btnFullscreen').click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.id)).toBe('playArea');
  await expect(page.locator('#botTime')).toBeVisible();
  await expect(page.locator('#gameTime')).toBeVisible();
  await expect(page.locator('#yourTime')).toBeVisible();
  const board = await page.locator('#board').boundingBox();
  const times = await page.locator('#gameTime').boundingBox();
  expect(board.y + board.height).toBeLessThanOrEqual(page.viewportSize().height);
  expect(times.x + times.width).toBeLessThan(board.x); // on desktop, the panel is left of the board
  await page.locator('#btnFullscreen').click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement)).toBeNull();
});

test('mobile fullscreen keeps the board and all three elapsed times together', async ({page}) => {
  await page.setViewportSize({width:390, height:780});
  await page.locator('#btnFullscreen').click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.id)).toBe('playArea');
  for (const id of ['board', 'botTime', 'gameTime', 'yourTime']) {
    const box = await page.locator(`#${id}`).boundingBox();
    expect(box.y + box.height).toBeLessThanOrEqual(780);
  }
  expect(await page.evaluate(() => document.querySelector('#playArea').scrollWidth <= innerWidth)).toBeTruthy();
});

test('reload restores the normal setup and new games reset the stopwatch', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  await page.locator('[data-square="e2"]').click();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  await expect(page.locator('#yourLastMove')).toHaveText(/Last move [\d.]+ s \(\d+ ms\)/);
  await page.locator('#btnNewTop').click();
  await expect(page.locator('#moveCount')).toHaveText('0 moves');
  await expect(page.locator('[data-square="e2"]')).toHaveAttribute('aria-label', 'e2, white pawn');
  await expect(page.locator('#yourLastMove')).toHaveText('Last move —');
  const reset = await (await page.request.get('/api/state')).json();
  expect(reset.game_elapsed).toBeLessThan(1.5);
  await page.locator('[data-square="e2"]').click();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  await page.reload();
  await expect(page.locator('#connectionBadge')).toHaveClass(/online/);
  await expect(page.locator('#moveCount')).toHaveText('0 moves');
  await expect(page.locator('[data-square="e2"]')).toHaveAttribute('aria-label', 'e2, white pawn');
  await expect(page.locator('[data-square="e4"]')).toHaveAttribute('aria-label', 'e4, empty');
  await expect(page.locator('#yourLastMove')).toHaveText('Last move —');
});

test('local game moves, undo restores it, and keyboard shortcuts work', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  await page.locator('[data-square="e2"]').click();
  await expect(page.locator('[data-square="e4"] .legal-dot')).toBeVisible();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  await expect(page.locator('[data-square="e4"] .piece')).toBeVisible();
  await page.locator('#btnUndo').click();
  await expect(page.locator('#moveCount')).toHaveText('0 moves');
  await expect(page.locator('[data-square="e2"] .piece')).toBeVisible();
  await page.keyboard.press('f');
  await expect(page.locator('.square').first()).toHaveAttribute('data-square', 'h1');
  await expect(page.locator('.square').first().locator('.coord.rank')).toHaveText('1');
  await page.locator('[data-square="e2"]').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-square="d2"]')).toBeFocused();
  await page.keyboard.press('c');
});

test('dragging a piece makes a legal move', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  await page.locator('[data-square="e2"]').dragTo(page.locator('[data-square="e4"]'));
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  await expect(page.locator('[data-square="e4"] .piece')).toBeVisible();
});

test('promotion offers four real piece choices, including underpromotion', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  for (const uci of ['a2a4', 'h7h5', 'a4a5', 'h5h4',
                    'a5a6', 'h4h3', 'a6b7', 'h3g2']) {
    const response = await page.request.post('/api/move', {
      data:{from:uci.slice(0, 2), to:uci.slice(2, 4)},
    });
    expect(response.ok(), `${uci}: ${await response.text()}`).toBeTruthy();
  }
  await expect(page.locator('#moveCount')).toHaveText('8 moves');
  await expect(page.locator('#matchTag')).toHaveText('WHITE TO PLAY');
  await expect(page.locator('[data-square="b7"] .piece')).toBeVisible();
  await page.locator('[data-square="b7"]').click();
  await page.locator('[data-square="a8"]').click();
  await expect(page.locator('#promotion')).toBeVisible();
  await expect(page.locator('.promotion-choice')).toHaveCount(4);
  await page.getByRole('button', {name:'Knight'}).click();
  await expect(page.locator('#promotion')).toBeHidden();
  await expect(page.locator('[data-square="a8"]')).toHaveAttribute('aria-label', 'a8, white knight');
  await expect(page.locator('#movesList')).toContainText('bxa8=N');
  await expect(page.locator('#bottomCaptured img')).toHaveCount(2); // black pawn and rook
  await expect(page.locator('#topCaptured img')).toHaveCount(1); // white pawn, not a promoted pawn
});

test('board annotations clear and PGN downloads actual moves', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  await page.locator('[data-square="e4"]').click({button:'right'});
  await expect(page.locator('[data-square="e4"]')).toHaveClass(/marked/);
  const [from, to] = await page.locator('#board').evaluate(element =>
    ['e2', 'e4'].map(square => {
      const {x, y, width, height} = element.querySelector(`[data-square="${square}"]`).getBoundingClientRect();
      return {x:x + width / 2, y:y + height / 2};
    }));
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({button:'right'});
  await page.mouse.move(to.x, to.y, {steps:5});
  await page.mouse.up({button:'right'});
  await expect(page.locator('#arrowsSvg line')).toHaveCount(1);
  await page.locator('#btnNewTop').focus();
  await page.keyboard.press('c');
  await expect(page.locator('#arrowsSvg line')).toHaveCount(0);
  await expect(page.locator('[data-square="e4"]')).not.toHaveClass(/marked/);
  await page.locator('[data-square="e2"]').click();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#btnDownloadPGN').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('chess-garden.pgn');
  const text = await readFile(await download.path(), 'utf8');
  expect(text).toContain('[Event "Chess Garden"]');
  expect(text).toContain('1. e4 *');
});

test('the bot turn rejects queued moves and undo still cancels its search', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#thinkDelay').selectOption('1.5');
  await page.locator('#btnNewTop').click();
  await page.locator('[data-square="e2"]').click();
  await page.locator('[data-square="e4"]').click();
  await expect(page.locator('#matchTag')).toHaveText('BOT IS THINKING');
  await page.locator('[data-square="g1"]').click();
  await page.locator('[data-square="f3"]').click();
  await expect(page.locator('[data-square="g1"]')).not.toHaveClass(/selected/);
  expect((await page.request.post('/api/premove', {data:{from:'g1',to:'f3'}})).status()).toBe(404);
  expect((await page.request.post('/api/move', {data:{from:'g1',to:'f3',premove:true}})).status()).toBe(400);
  await expect(page.locator('#moveCount')).toHaveText('1 move');
  await page.locator('#btnUndo').click();
  await expect(page.locator('#moveCount')).toHaveText('0 moves');
  await expect(page.locator('[data-square="e2"] .piece')).toBeVisible();
});

test('touchscreen taps can play on a narrow board', async ({browser}) => {
  const context = await browser.newContext({viewport:{width:390,height:780}, hasTouch:true,
                                            baseURL:'http://127.0.0.1:8000'});
  const page = await context.newPage();
  try {
    await page.goto('/');
    await expect(page.locator('#connectionBadge')).toHaveClass(/online/);
    await page.locator('[data-square="e2"]').tap();
    await expect(page.locator('[data-square="e4"] .legal-dot')).toBeVisible();
    await page.locator('[data-square="e4"]').tap();
    await expect(page.locator('#moveCount')).toHaveText('1 move');
  } finally {
    await context.close();
  }
});

test('a draw needs both players to agree', async ({page}) => {
  await page.locator('#preferences').evaluate(element => { element.open = true; });
  await page.locator('#botEnabled').uncheck();
  await page.locator('#btnNewCard').click();
  await expect(page.locator('#btnAccept')).toBeDisabled();
  await page.locator('#btnOffer').click();
  await expect(page.locator('#btnAccept')).toBeEnabled();
  await page.locator('#btnAccept').click();
  await expect(page.locator('#statusTitle')).toContainText('Draw agreed');
  await expect(page.locator('#btnOffer')).toBeDisabled();
});

for (const width of [360, 390, 768, 1440]) {
  test(`responsive at ${width}px without horizontal overflow`, async ({page}) => {
    await page.setViewportSize({width, height:800});
    await expect(page.locator('#board')).toBeVisible();
    const board = await page.locator('#board').boundingBox();
    expect(board.width).toBeGreaterThan(250);
    expect(Math.abs(board.width - board.height)).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    if (width < 680) {
      const coach = await page.locator('.coach-card').boundingBox();
      const moves = await page.locator('.move-panel').boundingBox();
      expect(Math.abs(coach.width - moves.width)).toBeLessThan(2);
    }
  });
}
