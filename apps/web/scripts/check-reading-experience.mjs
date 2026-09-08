/** Browser regression fixture. Run against `npm run dev` with Playwright installed. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.READING_TEST_URL || 'http://127.0.0.1:3100';
const output = process.env.READING_SCREENSHOTS || '../../artifacts/reading-review';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [];
const posts = [];
const book = { id: 'garden', book_id: 'garden', title: 'The Garden at Evening', author: 'Mara Ellis', filename: 'garden.epub', file_type: 'epub', file_size_bytes: 42000, total_chars: 3700, ingest_status: 'completed', created_at: '2026-09-01T10:00:00Z', section_count: 2, session_count: 1, last_session_at: '2026-09-06T10:00:00Z', has_audiobook: false, reading_progress_pct: 12, current_unit_title: 'The first light' };
// Original fixture prose, never inserted into the real library.
const paragraphs = [
  'The house had been quiet for so long that Eleanor had begun to mistake its silence for a kind of agreement. Each morning she opened the shutters, put the kettle on, and waited for the garden to tell her what had changed.',
  'It was a small garden. A pear tree leaned against the far wall, and below it the beds ran in crooked lines, as though someone had begun with a plan and gradually thought better of it. There were herbs she knew by touch and flowers whose names she had forgotten.',
  'There are things a garden knows that a house can only guess at. The weather, for instance. The particular weight of a bird on a branch. How to hold something for a season and then, without ceremony, let it go.',
  'She carried her tea outside. The stone step was still cool beneath her bare feet. Beyond the wall, a bicycle rattled past, followed by the ordinary sounds of a town beginning its day. For once, none of those sounds seemed to require anything of her.',
  'Her father had planted the pear tree in the year she was born. She had always been told this as if it established a connection, as if the two of them had made some early promise to keep growing. Looking at it now, she wondered whether a tree ever felt obliged to become anything in particular.',
  'A leaf turned in the pale light. Eleanor set down her cup and reached for the gate. She had no reason to open it, except that she had spent a great many mornings leaving it closed.'
];
const text1 = paragraphs.join('\n\n');
const text2 = 'By afternoon the light had moved to the other side of the wall. Eleanor found a letter tucked beneath a stone, its edges softened by the rain.\n\nShe recognized the handwriting before she read the name. Some forms of memory arrive before language.\n\nShe sat on the step and unfolded the page, taking her time. The garden went on being a garden.';
const quote1 = 'There are things a garden knows that a house can only guess at.';
const quote2 = 'Some forms of memory arrive before language.';
const section = (id, order, title) => ({ id, title, section_type: 'chapter', order_index: order, reading_time_min: 12, page_start: null, page_end: null, preview_text: '' });
const sections = [section('s1', 0, 'The first light'), section('s2', 1, 'The letter')];
const fullText = text1 + '\n\n' + text2;
function pageData(p, size = 1800) {
  const boundary = target => {
    if (target <= 0) return 0;
    if (target >= fullText.length) return fullText.length;
    if (/\s/.test(fullText[target-1]) || /\s/.test(fullText[target])) return target;
    const space = fullText.lastIndexOf(' ', target-1);
    return space >= Math.max(0, target - Math.min(120, size/2)) ? space + 1 : target;
  };
  const start = boundary((p-1)*size), end = boundary(p*size);
  const chunks = [{ chunk_id: 'c1', section_id: 's1', char_start: 0, char_end: text1.length }, { chunk_id: 'c2', section_id: 's2', char_start: text1.length+2, char_end: fullText.length }].filter(chunk => chunk.char_start < end && chunk.char_end > start);
  return { ...book, page: p, total_pages: Math.ceil(fullText.length/size), page_size: size, text: fullText.slice(start, end), char_start: start, char_end: end, current_section_id: chunks[0].section_id, current_section_title: sections[chunks[0].section_id === 's1' ? 0 : 1].title, current_section_order: chunks[0].section_id === 's1' ? 0 : 1, chunks };
}
const cite = { chunk_id: 'c1', text: quote1, char_start: text1.indexOf(quote1), char_end: text1.indexOf(quote1) + quote1.length, verified: true, match_type: 'exact' };
const histories = { companion: [], club: [{ id: 'opening', role: 'facilitator', content: 'Let’s stay with the garden for a moment. Eleanor seems to be learning a way of paying attention that asks very little of her. What do you notice about the way the house and the garden differ?', citations: [cite], created_at: '2026-09-06T10:00:00Z' }, { id: 'reader-old', role: 'user', content: 'The garden lets things change. The house seems to hold them still.', citations: [], created_at: '2026-09-06T10:01:00Z' }, { id: 'ell', role: 'close_reader', content: 'That difference is there in the verbs: the house can only “guess,” while the garden “knows.” I’m interested in how this reverses the usual idea that shelter gives us certainty.\n\nDoes the garden feel more welcoming, or simply less demanding?', citations: [cite], created_at: '2026-09-06T10:02:00Z' }] };
let prefs = { theme: 'cream-daylight', font_family: 'serif', font_size_px: 20, line_height: 1.75, measure_ch: 62, focus_reading: false, focus_reading_intensity: 40 };
let failNextPage = false;
async function fixture(context) {
  await context.route('**/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' } });
    if (req.method() === 'POST' || req.method() === 'PATCH') posts.push({ path, body: req.postDataJSON() });
    if (path === '/v1/books') return json({ books: [book, { ...book, id: 'walden', title: 'Walden', author: 'Henry David Thoreau', reading_progress_pct: 0 }, { ...book, id: 'room', title: 'A Room of One’s Own', author: 'Virginia Woolf', reading_progress_pct: 0 }, { ...book, id: 'meditations', title: 'Meditations', author: 'Marcus Aurelius', reading_progress_pct: 0 }] });
    if (path.endsWith('/bindery/status')) return json({ paused: false, queued: 0, processing: 0, failed_recent: 0 });
    if (path.endsWith('/local/folders')) return json({ books_dir: '/books', total_books: 4, folders: [], root_book_count: 4 });
    if (path.endsWith('/reading-prefs')) { if (req.method() === 'PATCH') prefs = { ...prefs, ...req.postDataJSON() }; return json(prefs); }
    if (path === '/v1/books/garden/reader') { if (failNextPage) { failNextPage = false; return json({ detail: 'test outage' }, 503); } return json(pageData(Number(url.searchParams.get('page') || 1), Number(url.searchParams.get('page_size') || 1800))); }
    if (path === '/v1/books/garden/companion') return json({ session_id: 'companion', remembered_turns: histories.companion.length });
    if (path.endsWith('/reader-notes')) {
      const p = req.postDataJSON().page, current = pageData(p, req.postDataJSON().page_size);
      const quote = current.text.includes(quote1) ? quote1 : current.text.trim().split(/[.!?]/)[0] + (current.text.includes('.') ? '.' : '');
      const start = current.char_start + current.text.indexOf(quote);
      const chunk = current.chunks.find(c => c.char_start <= start && c.char_end >= start + quote.length);
      return json({ notes: chunk ? [{ id: `note${p}`, question: p === 1 ? 'What kind of knowing belongs to the garden? Is it something Eleanor is beginning to learn?' : 'What changes as you stay with this passage?', quote, char_start: start, char_end: start + quote.length, chunk_id: chunk.chunk_id, section_id: chunk.section_id, verified: true }] : [], cached: true });
    }
    if (path.endsWith('/reader-location')) return json({ page: Math.floor(cite.char_start / Number(url.searchParams.get('page_size') || 1800)) + 1, section_id: 's1', char_start: cite.char_start });
    if (path.endsWith('/explore')) { const idx = url.searchParams.get('section_id') === 's2' ? 1 : 0; const text = idx ? text2 : text1; return json({ ...book, sections, active_section: { ...sections[idx], text, chunks: [{ chunk_id: `c${idx+1}`, section_id: `s${idx+1}`, char_start: 0, char_end: text.length }], source_refs: [], chunk_count: 1 }, audiobook_matches: [], has_local_audiobook: false, progress: { resume_section_id: 's1', reading_progress_pct: 12 } }); }
    if (path === '/v1/books/garden') return json(book);
    if (path === '/v1/sessions/start') return json({ session_id: 'club' });
    const sessionMatch = path.match(/^\/v1\/sessions\/(companion|club)(.*)$/);
    if (sessionMatch) {
      const [, id, suffix] = sessionMatch;
      if (!suffix) return json({ session_id: id, book_id: 'garden', sections, current_phase: 'discussion', mode: 'conversation', is_active: true, preferences: { experience_mode: 'text', discussion_style: 'cozy' } });
      if (suffix === '/messages') return json({ messages: histories[id] });
      if (suffix === '/message/stream') {
        const content = 'I remember your thought about the garden making room for change. The contrast with the house gives that idea a little more weight. What would it mean for Eleanor to let the gate stand open?';
        const msg = { id: `saved-${histories[id].length}`, role: 'facilitator', content, citations: [cite], created_at: new Date().toISOString() };
        histories[id].push({ id: `user-${histories[id].length}`, role: 'user', content: req.postDataJSON().content, citations: [], created_at: new Date().toISOString() }, msg);
        const events = [{ type: 'message_start', role: 'facilitator', sequence: 1, sentence_events: true }, { type: 'message_delta', role: 'facilitator', delta: content.slice(0, 85), sequence: 2 }, { type: 'message_delta', role: 'facilitator', delta: content.slice(0, 85), sequence: 2 }, { type: 'message_delta', role: 'facilitator', delta: content.slice(85), sequence: 3 }, { type: 'message_end', role: 'facilitator', ...(id === 'companion' ? {} : { content }), citations: [cite], message_id: msg.id, sequence: 4 }, { type: 'done', sequence: 5 }];
        return route.fulfill({ contentType: 'text/event-stream', body: events.map(e => `data: ${JSON.stringify(e)}\r\n\r\n`).join('') });
      }
      if (suffix.endsWith('/feedback') || suffix === '/preferences') return json({ ok: true });
    }
    if (path === '/v1/auth/status') return json({ authenticated: false, providers: [{ provider: 'openai', label: 'OpenAI', configured_auth_mode: 'api_key', connected: true, oauth_supported: false }, { provider: 'anthropic', label: 'Anthropic', configured_auth_mode: 'api_key', connected: false, oauth_supported: false }, { provider: 'google', label: 'Google Gemini', configured_auth_mode: 'oauth', connected: false, oauth_supported: true, oauth_ready: false }] });
    throw new Error(`Unmocked request: ${req.method()} ${path}`);
  });
}
const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, reducedMotion: 'reduce' });
await fixture(context);
const page = await context.newPage();
page.on('pageerror', e => errors.push(e.message));
await page.goto(base); await page.getByRole('heading', { name: 'Your library', exact: true }).waitFor();
await page.getByRole('heading', { name: 'The Garden at Evening', exact: true }).first().waitFor();
await page.screenshot({ path: `${output}/landing.png`, fullPage: true });
await page.goto(`${base}/books/garden/read`);
await page.getByRole('button', { name: /Read with me/ }).click();
await page.getByRole('button', { name: /Talk about this/ }).waitFor();
assert.equal(await page.locator('.passage-mark').first().innerText(), quote1);
await page.screenshot({ path: `${output}/reader-fresh.png`, fullPage: false });
await page.getByRole('button', { name: 'Paper and typography settings' }).click();
await page.getByRole('button', { name: /Well-loved/ }).click();
await page.getByRole('button', { name: 'Close reading settings' }).click();
await page.waitForFunction(() => document.querySelector('.lite-reader')?.classList.contains('lite-aged-paper'));
await page.screenshot({ path: `${output}/reader-paperback.png`, fullPage: false });
for (const [label, theme, filename] of [['Old favorite', 'archive-paper', 'reader-archive'], ['Bright white', 'paper-white', null], ['Evening', 'lamplight-dark', 'reader-evening'], ['Well-loved', 'aged-paper', null]]) {
  await page.getByRole('button', { name: 'Paper and typography settings' }).click();
  await page.getByRole('button', { name: new RegExp(label) }).click();
  await page.getByRole('button', { name: 'Close reading settings' }).click();
  assert.ok(await page.locator(`.lite-${theme}`).count());
  if (filename) await page.screenshot({ path: `${output}/${filename}.png`, fullPage: false });
}
await page.getByRole('button', { name: 'Paper and typography settings' }).click();
const savedBionic = page.waitForResponse(res => res.url().includes('/reading-prefs') && res.request().method() === 'PATCH' && res.request().postDataJSON().focus_reading === true && res.request().postDataJSON().focus_reading_intensity === 60);
await page.getByRole('switch', { name: 'Bionic text' }).click();
await page.getByRole('slider', { name: 'Bionic emphasis', exact: true }).press('End');
assert.ok(await page.locator('.bionic-preview .fr-b').count());
await page.getByRole('button', { name: 'Close reading settings' }).click();
await savedBionic;
await page.locator('.lite-prose .fr-b').first().waitFor();
assert.equal(await page.locator('.passage-mark').first().innerText(), quote1, 'bionic emphasis keeps citation text intact');
await page.screenshot({ path: `${output}/reader-bionic.png`, fullPage: false });
await page.reload();
await page.locator('.lite-prose .fr-b').first().waitFor();
await page.getByRole('button', { name: /Talk about this/ }).waitFor();
assert.equal(await page.locator('.passage-mark').first().innerText(), quote1);
await page.getByRole('button', { name: /Talk about this/ }).click();
await page.getByRole('textbox', { name: 'Your thought or question' }).fill('The garden makes room for change.');
await page.getByRole('textbox', { name: 'Your thought or question' }).press('ArrowRight');
assert.match(page.url(), /page=1/);
await page.getByRole('button', { name: 'Send to your companion' }).click();
await page.getByText('I remember your thought about the garden', { exact: false }).waitFor();
assert.equal(await page.locator('.companion-message.from-companion').count(), 1);
assert.equal(await page.locator('.companion-message.from-companion .companion-message-prose').innerText(), histories.companion.at(-1).content, 'partial final event preserves streamed text without replaying duplicate deltas');
await page.getByRole('button', { name: 'Next page', exact: true }).click();
await page.waitForURL('**?page=2&size=*');
await page.getByRole('tab', { name: /In the margin/ }).click();
await page.getByText('What changes as you stay with this passage?', { exact: true }).waitFor();
assert.notEqual(await page.locator('.passage-mark').first().innerText(), quote1);
await page.getByRole('tab', { name: 'Our conversation', exact: true }).click();
await page.locator('.companion-citation').first().click();
await page.waitForURL('**?page=1&size=*');
await page.waitForFunction(() => document.querySelector('.lite-prose')?.textContent?.includes('The house had been quiet'));
assert.ok(await page.locator('.passage-mark').count());
await page.getByRole('button', { name: 'Next page', exact: true }).click();
await page.waitForURL('**?page=2&size=*');
await page.goto(`${base}/books/garden/read`); await page.waitForURL('**?page=2&size=*');
assert.ok(await page.locator('.lite-aged-paper').count(), 'paper preference persists');
failNextPage = true;
await page.getByRole('button', { name: 'Previous page', exact: true }).click();
await page.getByRole('alert').filter({ hasText: 'This page couldn’t' }).waitFor();
await page.getByRole('button', { name: 'Try again', exact: true }).first().click();
await page.waitForURL('**?page=1&size=*');
await page.goto(`${base}/books/garden`);
await page.getByRole('button', { name: 'Start a book club session', exact: true }).click();
await page.waitForURL('**/sessions/club');
await page.getByText('The garden lets things change.', { exact: false }).waitFor();
await page.locator('.cite-bracket').first().click();
await page.locator('.open-book-prose [data-selected="true"]').first().waitFor();
await page.screenshot({ path: `${output}/book-club.png`, fullPage: false });
await page.goto(`${base}/settings`); await page.getByText('API key configured', { exact: true }).waitFor();
await page.screenshot({ path: `${output}/settings.png`, fullPage: false });
const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
await fixture(mobile);
const phone = await mobile.newPage(); phone.on('pageerror', e => errors.push(e.message));
await phone.goto(`${base}/books/garden/read`);
await phone.getByRole('button', { name: 'Next page', exact: true }).waitFor();
assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no horizontal overflow on phone');
assert.ok(await phone.locator('.lite-page').evaluate(el => el.getBoundingClientRect().height < innerHeight), 'a phone page fits its viewport');
await phone.screenshot({ path: `${output}/reader-mobile.png`, fullPage: false });
await phone.getByRole('button', { name: 'Toggle reading companion' }).click();
await phone.getByRole('dialog').waitFor();
await phone.getByRole('button', { name: /Read with me/ }).click();
await phone.getByRole('button', { name: /Talk about this/ }).waitFor();
await phone.screenshot({ path: `${output}/companion-mobile.png`, fullPage: false });
await phone.getByRole('button', { name: 'Close companion' }).click();
assert.equal(await phone.getByRole('dialog').count(), 0);
await phone.locator('.lite-page').evaluate(el => {
  const start = new Touch({ identifier: 1, target: el, clientX: 320, clientY: 300 });
  el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [start], changedTouches: [start] }));
  const end = new Touch({ identifier: 1, target: el, clientX: 60, clientY: 310 });
  el.dispatchEvent(new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [end] }));
});
await phone.waitForURL('**?page=2&size=*');
await phone.goto(`${base}/books/garden/sessions/club`);
await phone.locator('.cite-bracket').first().waitFor(); await phone.locator('.cite-bracket').first().click();
await phone.getByRole('dialog').waitFor();
await phone.locator('.open-book-prose [data-selected="true"]').first().waitFor();
await phone.getByRole('button', { name: 'Close book panel' }).click();
assert.equal(await phone.getByRole('dialog').count(), 0);
assert.deepEqual(errors, [], 'no browser runtime errors');
assert.ok(posts.some(p => p.path.endsWith('/companion') && p.body.page === 2), 'updates companion to new page');
const turningContext = await browser.newContext({ viewport: { width: 1440, height: 1080 }, reducedMotion: 'no-preference' });
await fixture(turningContext);
const turningPage = await turningContext.newPage();
await turningPage.goto(`${base}/books/garden/read`);
await turningPage.getByRole('button', { name: 'Next page', exact: true }).click();
await turningPage.locator('.paper-turn-sheet').waitFor();
assert.equal(await turningPage.locator('.paper-turn-sheet').getAttribute('aria-hidden'), 'true');
await turningPage.waitForFunction(() => !document.querySelector('.paper-turn-sheet'));
assert.match(turningPage.url(), /page=2/);
await browser.close();
console.log('PASS: desktop/mobile reading, paper persistence, exact highlights, page retry/resume, companion streaming, citation navigation, book club and dialogs.');
