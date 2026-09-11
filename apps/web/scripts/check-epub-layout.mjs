/** Structured and legacy EPUB rendering; all prose and API responses are fixtures. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.READING_TEST_URL || 'http://127.0.0.1:3100';
const output = process.env.READING_SCREENSHOTS || '../../artifacts/reading-review';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [];
const length = text => Array.from(text).length;
let fullText = '';
const blocks = [];
function add(kind, text, properties = {}, annotated = []) {
  if (fullText) fullText += '\n\n';
  const start = length(fullText);
  const marks = annotated.map(([kind, quote]) => {
    const offset = length(text.slice(0, text.indexOf(quote)));
    return { kind, char_start: start + offset, char_end: start + offset + length(quote) };
  });
  blocks.push({ kind, char_start: start, char_end: start + length(text), marks, ...properties });
  fullText += text;
}
add('heading', 'The first morning', { level: 1 });
const quote = '🕯 She was almost ready. The rereading began.';
add('paragraph', quote, {}, [['emphasis', 'almost'], ['strong', 'read']]);
add('paragraph', 'A second paragraph, with a quiet thought.');
add('quote', 'Let the window stay open.');
add('list_item', 'Listen.', { list_label: '3.' });
add('list_item', 'Wait.', { list_label: '-9999.' });
add('paragraph', 'One line.\nAnother line.', {}, [['line_break', '\n']]);
add('preformatted', '  a    b\n    c');
add('paragraph', 'H2O and x2; hello().', {}, [['subscript', '2'], ['code', 'hello()']]);
for (let i = 0; i < 14; i++) add('paragraph', 'The light moved across the room. She watched it reach the empty chair, then the edge of the table. A page waited beside her cup.');
const chars = Array.from(fullText);
function pageData(page, size) {
  const start = Math.min(chars.length, (page - 1) * size), end = Math.min(chars.length, page * size);
  return { book_id: 'layout', title: 'At the window', author: null, page, page_size: size, total_chars: chars.length,
    total_pages: Math.ceil(chars.length / size), edition_id: 'a'.repeat(64), char_start: start, char_end: end,
    current_section_id: 'one', current_section_title: 'The first morning', current_section_order: 0,
    text: chars.slice(start, end).join(''), chunks: [{ chunk_id: 'chunk', section_id: 'one', char_start: 0, char_end: chars.length }],
    blocks: blocks.filter(b => b.char_start < end && b.char_end > start).map(b => ({ ...b,
      char_start: Math.max(start, b.char_start), char_end: Math.min(end, b.char_end), continued: start > b.char_start,
      marks: b.marks.filter(m => m.char_start < end && m.char_end > start).map(m => ({ ...m, char_start: Math.max(start, m.char_start), char_end: Math.min(end, m.char_end) })) })) };
}
async function fixture(context, variant = 'structured') {
  await context.addInitScript(() => localStorage.setItem('readagain.book.layout.companion', 'on'));
  await context.route('**/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const json = value => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) });
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204 });
    if (path.endsWith('/reading-prefs')) return json({ theme: 'cream-daylight', font_family: 'serif', font_size_px: 20, line_height: 1.75, measure_ch: 62, focus_reading: false, focus_reading_intensity: 40, ...(request.method() === 'PATCH' ? request.postDataJSON() : {}) });
    if (path.endsWith('/reader')) {
      const result = pageData(Number(url.searchParams.get('page') || 1), Number(url.searchParams.get('page_size') || 1800));
      if (variant === 'legacy') {
        result.text = 'The first morning\nThe re\nread\ning began.\nA separate paragraph.';
        result.char_end = length(result.text);
        result.blocks = [{ kind: 'heading', level: 1, char_start: 0, char_end: 17, marks: [] },
          { kind: 'paragraph', char_start: 18, char_end: 40, marks: [{ kind: 'join', char_start: 24, char_end: 25 }, { kind: 'strong', char_start: 25, char_end: 29 }, { kind: 'join', char_start: 29, char_end: 30 }] },
          { kind: 'paragraph', char_start: 41, char_end: length(result.text), marks: [] }];
      } else if (variant === 'partial') result.blocks = result.blocks.filter(b => b.kind === 'heading');
      return json(result);
    }
    if (path.endsWith('/companion')) return json({ session_id: 'layout-session', reading_position: { page: request.postDataJSON().page, page_size: request.postDataJSON().page_size, edition_id: 'a'.repeat(64) } });
    if (path.endsWith('/reader-notes')) return json({ notes: variant === 'structured' && request.postDataJSON().page === 1 ? [{ id: 'note', question: 'What changes when she begins again?', quote, char_start: blocks[1].char_start, char_end: blocks[1].char_end, chunk_id: 'chunk', section_id: 'one', verified: true }] : [], cached: true });
    if (path.endsWith('/messages')) return json({ messages: [] });
    if (path === '/v1/sessions/layout-session') return json({ session_id: 'layout-session', book_id: 'layout', mode: 'conversation', is_active: true, current_phase: 'discussion', sections: [{ id: 'one', title: 'The first morning', section_type: 'chapter', order_index: 0 }], preferences: { experience_mode: 'text', discussion_style: 'cozy' } });
    if (path === '/v1/books/layout') return json({ id: 'layout', title: 'At the window', author: null, filename: 'window.epub', file_type: 'epub', file_size_bytes: 3000, ingest_status: 'completed', created_at: '2026-09-01T10:00:00Z' });
    throw new Error(`Unmocked EPUB layout request: ${request.method()} ${path}`);
  });
}

try {
  for (const viewport of [{ width: 1440, height: 1080 }, { width: 390, height: 844 }]) {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
    await fixture(context);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/books/layout/read`);
    const paper = page.getByRole('article', { name: 'Book page' });
    await paper.locator('.passage-mark').waitFor();
    assert.equal(await paper.getByRole('heading', { name: 'The first morning' }).count(), 1, 'source heading appears once');
    assert.equal(await paper.locator('.passage-mark').count(), 1, 'one clickable quotation across inline marks');
    assert.equal(await paper.locator('.passage-mark').innerText(), quote, 'Unicode positions preserve the whole marked quotation');
    assert.equal(await paper.locator('em').innerText(), 'almost');
    assert.equal(await paper.locator('strong').innerText(), 'read');
    assert.ok(await paper.locator('p').count() >= 2, 'real paragraphs remain separate');
    assert.equal(await paper.locator('p').first().evaluate(el => getComputedStyle(el, '::first-letter').float), 'none', 'source headings do not activate the old drop cap');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (viewport.width > 900) {
      assert.equal(await paper.locator('blockquote').innerText(), 'Let the window stay open.');
      assert.equal(await paper.getByRole('listitem').count(), 2);
      assert.equal(await paper.locator('.prose-list-label').last().evaluate(el => el.getBoundingClientRect().left >= el.closest('.lite-prose').getBoundingClientRect().left), true, 'long list labels stay inside the text column');
      assert.equal(await paper.locator('pre').textContent(), '  a    b\n    c');
      assert.equal(await paper.locator('.prose-line-break').evaluate(el => getComputedStyle(el).whiteSpace), 'pre');
    }
    await page.screenshot({ path: `${output}/epub-${viewport.width > 900 ? 'desktop' : 'mobile'}.png`, fullPage: false });
    await page.getByRole('button', { name: 'Paper and typography settings' }).click();
    await page.getByRole('switch', { name: 'Bionic text' }).click();
    await page.getByRole('button', { name: 'Close reading settings' }).click();
    await paper.locator('.fr-b').first().waitFor();
    assert.equal(await paper.locator('.passage-mark').innerText(), quote);
    assert.equal(await paper.locator('em').innerText(), 'almost');
    assert.equal(await paper.locator('strong').evaluate(el => [el, ...el.querySelectorAll('*')].every(node => Number(getComputedStyle(node).fontWeight) >= 600)), true, 'Bionic text preserves the author’s bold emphasis');
    await paper.locator('.passage-mark').click();
    assert.equal(await page.locator('.margin-question.is-selected q').innerText(), quote);
    await page.getByRole('button', { name: 'Talk about this', exact: false }).click();
    await page.locator('.companion-selected p').waitFor();
    assert.equal(await page.locator('.companion-selected p').innerText(), `“${quote}”`);
    if (viewport.width <= 900) {
      await page.getByRole('button', { name: 'Close companion' }).click();
      // Capture the fixed viewport; full-page capture can change pagination dimensions.
      await page.screenshot({ path: `${output}/epub-bionic-mobile.png`, fullPage: false });
    }
    await page.getByRole('button', { name: 'Next page', exact: true }).click();
    await page.waitForURL('**?page=2&size=*');
    await page.waitForFunction(() => document.querySelector('.lite-page')?.getAttribute('aria-busy') === 'false');
    assert.equal(await paper.getByRole('heading').count(), 0, 'continuing pages do not repeat the chapter heading');
    await context.close();
  }
  for (const variant of ['legacy', 'partial']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, reducedMotion: 'reduce' });
    await fixture(context, variant);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/books/layout/read`);
    await page.locator('.lite-prose p').first().waitFor();
    if (variant === 'legacy') {
      assert.equal(await page.locator('.lite-prose p').first().innerText(), 'The rereading began.');
      assert.equal(await page.locator('.lite-prose p').nth(1).innerText(), 'A separate paragraph.');
    } else {
      assert.ok((await page.locator('.lite-prose').innerText()).includes('A second paragraph'), 'unmapped prose still renders');
      assert.ok((await page.locator('.lite-prose').innerText()).includes('A page waited beside her cup.'), 'fallback retains all paragraphs');
    }
    await context.close();
  }
  assert.deepEqual(errors, [], 'no EPUB browser runtime errors');
  console.log('PASS: EPUB paragraphs, source headings, emphasis, Unicode highlights, Bionic text, lists, verse, legacy recovery, fallback, and mobile continuation.');
} finally { await browser.close(); }
