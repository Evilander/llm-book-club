# ReadAgain reading experience review

Implemented September 7, 2026. The visual direction favors restraint, generous space, and a simple invitation to read.

## Why it felt off, and what changed

| Priority | Finding | Change |
| --- | --- | --- |
| High | Reading, setup, an obligatory session opener, and discussion felt like separate products. | Library books open directly into the reader. A companion sits beside the text; book-club setup has a simple chapter choice. Sessions open directly into the conversation. |
| High | The shelf mixed real books with invented marginal notes and decorative catalog information. | Removed fictional annotations, fake volume details, and vertical spines. Covers have readable titles and authors; progress comes from the library. |
| High | Retrieval chunks overlap. Joining them repeated text, and independently adjusted page boundaries could skip words. | A shared reading edition aligns actual overlapping text, preserves chunk mappings, and uses identical boundaries for the end of one page and the start of the next. |
| High | Citations used chunk-local offsets as section offsets, and the section lookup used the wrong ID. | Explicit chunk-to-reading mappings, Unicode code-point offsets, a citation-location endpoint, and exact text checks now connect a quotation to the page. Removed guessed page numbers. |
| High | Conversations were stored, but earlier sessions were absent from normal model context. | Native book recall retrieves earlier reader thoughts across sessions. The companion reuses its conversation across chapters and starts a continuation when the existing session limit is reached. |
| Medium | Fixed text amounts made phone pages extremely tall; the visual treatment was predominantly dark oxblood and brass. | Five subtle paper treatments, restrained typography, viewport-sensitive page lengths, saved reading position, and directional page turns with reduced-motion support. Bionic text adds optional word-prefix emphasis with a live preview and a saved 25–60% intensity. |
| Medium | Streaming could lose split frames, retain temporary message IDs, or erase accumulated content on a partial final event. | A buffered SSE decoder, sequence deduplication, canonical IDs, visible recovery states, and preservation of streamed content when final content is absent. |
| Medium | The mobile book drawer only displayed a scrim; automatic scrolling moved the reader during replies. | Functional Radix dialogs for both companion and book, independent scroll areas, and follow-scroll only when the reader is near the end. |
| Medium | Connection controls dominated the home page and API-key providers appeared disconnected even when configured. | A separate, quiet settings page reports configured keys accurately and presents only available sign-in actions. |

Primary files: [reader](../apps/web/components/lite-reader.tsx), [companion panel](../apps/web/components/reader-companion.tsx), [book club](../apps/web/components/discussion-stage.tsx), [visual styles](../apps/web/app/reading-room.css), [reading edition](../apps/api/app/services/reader_text.py), [companion API](../apps/api/app/routers/companion.py), [book recall](../apps/api/app/services/book_recall.py).

## Memory and grounding

The app owns memory in its existing database. No Audrey dependency, provider-side memory, or new credential store is needed for this local-library workflow.

- `DiscussionSession` and `Message` keep the actual conversations. The reader extends a companion session across visited chapters. At the configured message limit, it preserves the earlier session and creates a continuation; the reader can also reconnect without resending a failed message automatically.
- The model receives recent conversation history (the existing default is 50 messages) plus at most six earlier reader thoughts, each limited to 600 characters. Recall searches the same book, prefers query matches, and excludes sessions beyond the current chapter boundary. It is deterministic keyword recall, not an exhaustive or semantic account of everything ever discussed.
- Existing `BookMemory` context remains available. Earlier thoughts are explicitly labeled as untrusted conversation data and cannot substitute for evidence from the book.
- The companion receives the current page as its immediate context. The introductory slice context is also bounded by `MAX_CONTEXT_TOKENS` (default 4,000 estimated tokens); retrieval retains the selected chunk IDs. This prevents each newly visited chapter from appending its full text to every prompt.
- Margin questions are opt-in, at most two per page, and can be paused. The model returns a question and a literal quotation; the server finds the actual chunk and validates the exact quote within the current page. It ignores model-supplied chunk IDs and rejects invented, malformed, or off-page quotations.
- Margin questions are cached in message metadata, separate from visible conversation. The key hashes the prompt version, page number, page size, and exact page text. There is no expiry: changing the edition, pagination, or prompt version invalidates the cache. Requests are limited to 12/minute and outputs to 650 tokens. Concurrent uncached requests can still duplicate generation; a distributed single-flight mechanism is a future hardening step.

New endpoints: `POST /v1/books/{book_id}/companion`, `POST /v1/books/{book_id}/reader-notes`, and `GET /v1/books/{book_id}/reader-location`. Reader and explore responses now include assembled chunk spans. Reader `char_end` is exclusive; old clients that assumed an inclusive endpoint need this adjustment. Source positions and page sizes are saved together in the browser. Existing database columns are reused; no schema migration is required. New preference records default to fresh paper, 20px type, and 1.75 line spacing; existing preferences are preserved.

The current deployment model remains a local library. Book/session ownership must be enforced before hosting unrelated users together. Evidence is restricted to visited sections; an exact page-level spoiler barrier inside an opened chapter is not yet enforced. These changes do not claim that every model observation is correct: exact quote validation proves the quotation, not the interpretation.

## ChatGPT and Claude sign-in

Subscription sign-in is **not connected in this implementation**. The current OpenAI and Anthropic adapters continue to use their configured APIs; Google/Gemini retains its existing OAuth flow.

OpenAI documents ChatGPT sign-in for its Codex runtime. The official app server supports account login and streamed turns, making a local Codex adapter a possible route for a later integration. This is a separate runtime integration, with tool permissions and account isolation to design; a ChatGPT subscription token is not a generic replacement for an OpenAI API key. See [Codex authentication](https://developers.openai.com/codex/auth/) and [Codex app server](https://developers.openai.com/codex/app-server/). ChatGPT app OAuth instead authenticates ChatGPT to an application's own service; see [app authentication](https://developers.openai.com/apps-sdk/build/auth/).

Anthropic's current policy permits hosting its unmodified Claude Code binary when the end user authenticates through the native flow, and prohibits intermediating Claude.ai credentials in an application's own login flow. A native-runtime adapter is therefore a different integration from the app's Anthropic API adapter. See [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance). No subscription tokens or credentials were collected, copied, or reused during this work.

## Validation

- Full backend suite: **533 passed** using Python 3.12 with SQLite fixtures. Includes 21 new regressions for overlap removal, contiguous pages, Unicode offsets, verified questions, question caching, chapter/session reuse, conversation limits, bounded context, and memory scope. Provider output is mocked; these are deterministic checks, not live model-quality evaluations.
- Production build: `next build` passes, including static generation and TypeScript checks. `tsc --noEmit` also passes independently.
- SSE decoder: every possible split of a UTF-8/CRLF fixture, one-byte chunks, multiline data, incomplete/malformed events, and the total frame-size limit pass.
- Browser regression uses isolated request fixtures with original sample prose. Covers desktop and phone reading, all five paper choices, saved paper/page preferences, Bionic text and intensity persistence, exact highlights with emphasis enabled, current-page updates, discussion streaming, missing final content, duplicate-event handling, citation navigation, error retry, book-club navigation, swipe turns, page-turn animations, reduced motion, and focus-managed drawers. Screenshots are fixtures, not books added to the actual library.
- CodeRabbit reviewed 29 files through its free CLI allowance. Its one finding—preserve accumulated text when a final stream event omits content—was verified, fixed, and added to the browser fixture. Later pagination refinements were checked locally. See [review output](../artifacts/reading-review/coderabbit.jsonl).

Reproduce:

```bash
# From the repository root, with the backend dependencies installed:
python -m pytest apps/api/tests -q
node apps/web/node_modules/typescript/bin/tsc --noEmit -p apps/web/tsconfig.json
node apps/web/scripts/check-event-stream.mjs

# With the web dev server and Playwright/Chromium installed:
cd apps/web
READING_TEST_URL=http://127.0.0.1:3000 node scripts/check-reading-experience.mjs
```

If Playwright is installed outside the app, set `PLAYWRIGHT_MODULE` to its absolute `index.mjs` path. On mounted drives that miss file notifications, start development with `WATCHPACK_POLLING=true npm run dev`.

[Landing preview](../artifacts/reading-review/landing.png) · [Fresh paper](../artifacts/reading-review/reader-fresh.png) · [Older paper](../artifacts/reading-review/reader-paperback.png) · [Book club](../artifacts/reading-review/book-club.png) · [Phone reader](../artifacts/reading-review/reader-mobile.png) · [Bionic text](../artifacts/reading-review/reader-bionic.png).
