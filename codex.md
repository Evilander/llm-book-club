# codex.md - LLM Book Club runbook for Codex

This file is a factual runbook for the current `B:\Projects\Claude\llm-book` workspace.

It should describe what exists now, how to run it, and which files/routes/settings are real. It should not try to act as the long-form product doctrine document. For behavior, taste, and higher-level operating rules, use `CLAUDE.md` and `AGENTS.md`.

## Current Architecture

The app is a grounded, multi-agent book discussion system with a local-library front end, a FastAPI backend, PostgreSQL + pgvector storage, Redis + RQ background work, and pluggable LLM / embeddings / reranking / TTS providers.

The main pipelines are:

1. Ingestion
2. Retrieval
3. Discussion
4. Voice

The frontend is a projection layer. The backend owns canonical state.

## Repo Map

Top-level:

- `apps/api/` - FastAPI backend
- `apps/web/` - Next.js frontend
- `docker-compose.yml` - local stack orchestration
- `CLAUDE.md` - operating manual for Claude
- `AGENTS.md` - step-up brief and research-oriented handoff

Backend files that matter most:

- `apps/api/app/main.py` - FastAPI app factory, routers, CORS
- `apps/api/app/db/models.py` - ORM schema
- `apps/api/app/ingest/` - extraction, chunking, ingest pipeline
- `apps/api/app/retrieval/search.py` - hybrid retrieval
- `apps/api/app/retrieval/selector.py` - session slice selection
- `apps/api/app/discussion/agents.py` - agents, citation parsing, verification
- `apps/api/app/discussion/engine.py` - orchestration, persistence, SSE streaming
- `apps/api/app/discussion/prompts.py` - role prompts and adult overlays
- `apps/api/app/routers/sessions.py` - session endpoints
- `apps/api/app/routers/library.py` - local library browse and explore
- `apps/api/app/routers/tts.py` - TTS endpoints
- `apps/api/app/routers/memory.py` - book memory endpoints
- `apps/api/app/services/media_library.py` - local media scanning and pairing

Frontend files that matter most:

- `apps/web/app/page.tsx` - library home page
- `apps/web/app/books/[bookId]/page.tsx` - session setup route
- `apps/web/app/books/[bookId]/sessions/[sessionId]/page.tsx` - discussion route
- `apps/web/app/layout.tsx` - shared header, fonts, toaster
- `apps/web/app/globals.css` - design tokens, after-dark mode, animations
- `apps/web/components/book-shelf.tsx` - library browse
- `apps/web/components/session-setup.tsx` - session configuration
- `apps/web/components/discussion-stage.tsx` - discussion UI, streaming, citations, audio
- `apps/web/components/voice-input.tsx` - speech-to-text input
- `apps/web/components/ui/citation-card.tsx` - citation display with verification
- `apps/web/components/ui/prompt-chip-rail.tsx` - conversation spark buttons
- `apps/web/components/ui/voice-roster.tsx` - agent identity roster
- `apps/web/components/ui/mode-banner.tsx` - after-dark mode banner
- `apps/web/components/ui/session-recap.tsx` - session summary card
- `apps/web/components/ui/screen-intro.tsx` - editorial section header
- `apps/web/tailwind.config.ts` - design tokens, font families, citation colors
- `design/llm-book-club.DESIGN.md` - full design system specification

## Data Model

Current core entities in `apps/api/app/db/models.py`:

- `Book`
- `Section`
- `Chunk`
- `DiscussionSession`
- `Message`
- `BookMemory`
- `ReadingUnit`
- `Note`
- `Achievement`

Relevant enums:

- `DiscussionMode`: `conversation`, `first_time`, `deep_dive`, `big_picture`, plus legacy `guided`, `socratic`, `poetry`, `nonfiction`
- `MessageRole`: `user`, `facilitator`, `close_reader`, `skeptic`, `system`
- `IngestStatus`: `queued`, `processing`, `completed`, `failed`

Important persisted fields:

- `Book.metadata_json` can hold source metadata such as `source_path`
- `DiscussionSession.section_ids` stores the active reading slice
- `DiscussionSession.preferences_json` stores session preferences such as style, voice, experience mode, and adult-room settings
- `Message.citations` stores verified citation data

## Current API Surface

Library endpoints in `apps/api/app/routers/library.py`:

- `GET /library/local`
- `GET /library/local/audiobooks`
- `POST /library/local/ingest`
- `GET /books/{book_id}/explore`

Session endpoints in `apps/api/app/routers/sessions.py`:

- `POST /sessions/start`
- `GET /sessions/{session_id}`
- `PATCH /sessions/{session_id}/preferences`
- `GET /sessions/{session_id}/messages`
- `POST /sessions/{session_id}/start-discussion`
- `POST /sessions/{session_id}/message`
- `POST /sessions/{session_id}/message/stream`
- `POST /sessions/{session_id}/challenge`
- `POST /sessions/{session_id}/advance-phase`
- `POST /sessions/{session_id}/summary`
- `POST /sessions/{session_id}/end`

TTS endpoints in `apps/api/app/routers/tts.py`:

- `POST /tts/synthesize`
- `POST /tts/stream`
- `GET /tts/voices`
- `GET /tts/agent-voices`

The live SSE route is `POST /sessions/{session_id}/message/stream`.

## Current Discussion Behavior

Per turn, the backend currently:

1. Persists the user message
2. Rebuilds conversation history from the database
3. Selects the active slice
4. Builds agent prompts with session preferences and retrieved evidence
5. Calls the LLM provider
6. Parses and verifies citations
7. Persists messages and citations
8. Streams events to the frontend over SSE

Current SSE event shape in the engine includes:

- `message_start`
- `message_delta`
- `sentence_ready`
- `message_end`
- `done`
- `error`

The event payloads include ordering / identity fields such as `event_id`, `turn_id`, and `sequence`. The frontend uses those to dedupe and order stream updates.

## Current Retrieval Behavior

Retrieval is hybrid:

- vector search over chunk embeddings
- PostgreSQL full-text search
- reciprocal rank fusion
- optional reranking

Session retrieval is slice-aware. The current engine passes allowed `section_ids` and `chunk_ids` through agent construction, and citation verification can reject citations outside the active slice.

## Current Voice Behavior

The TTS layer supports:

- one-shot synthesis
- streamed synthesis
- provider-specific voice listing
- per-agent voice mapping for discussion playback

The discussion frontend can drive sentence-level audio from streamed discussion text. The live route and the TTS route are separate concerns:

- discussion streaming: `POST /sessions/{session_id}/message/stream`
- TTS streaming: `POST /tts/stream`

## Current Library Behavior

Library endpoints currently support:

- scanning a configured local books directory
- scanning a configured local audiobooks directory
- browsing and searching local files
- ingesting a local book file
- exploring a book by section, including preview text and active section details
- pairing likely local audiobooks with an ingested book

## Current Settings Surface

Backend settings live in `apps/api/app/settings.py`.

Current environment variables and defaults:

- `DATABASE_URL` - required
- `REDIS_URL` - required
- `APP_ENV` - default `dev`
- `LLM_PROVIDER` - default `openai`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_MODEL` - default `gemini-2.0-flash`
- `GROK_API_KEY`
- `GROK_MODEL` - default `grok-3`
- `LOCAL_LLM_BASE_URL`
- `EMBEDDINGS_PROVIDER` - default `openai`
- `OPENAI_EMBEDDINGS_MODEL` - default `text-embedding-3-large`
- `LOCAL_EMBEDDINGS_BASE_URL`
- `LOCAL_EMBEDDINGS_MODEL` - default `BAAI/bge-m3`
- `RERANKER_PROVIDER` - default `none`
- `RERANKER_MODEL` - default `rerank-v3.5`
- `COHERE_API_KEY`
- `LOCAL_RERANKER_MODEL` - default `BAAI/bge-reranker-v2-m3`
- `TTS_PROVIDER` - default `vibevoice`
- `TTS_BASE_URL`
- `TTS_MODEL` - default `tts-1`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `EMBEDDING_CACHE_TTL` - default `3600`
- `MAX_UPLOAD_MB` - default `200`
- `BOOKS_DIR`
- `AUDIOBOOKS_DIR`
- `CORS_ORIGINS` - default `http://localhost:3000`
- `RATE_LIMIT_DEFAULT` - default `60/minute`
- `ADMIN_TOKEN` - shared secret for `/v1/admin/*`. When unset, admin is permissive only if `APP_ENV` is `dev`/`development`/`test`/`local`.
- `FAST_LLM_ENABLED` - default `true`. When true, routing/classification/summary calls use the cheap tier instead of the primary model.
- `ANTHROPIC_FAST_MODEL` - default `claude-haiku-4-5`
- `OPENAI_FAST_MODEL` - default `gpt-4.1-mini`
- `MAX_HISTORY_MESSAGES` - default `50`
- `MAX_CONTEXT_TOKENS` - default `4000`
- `MAX_TOKENS_PER_TURN` - default `2048`
- `MAX_SESSION_MESSAGES` - default `200`

Provider model pins (in `apps/api/app/providers/llm/`):

- Anthropic primary: `claude-sonnet-4-6`; fast tier: `claude-haiku-4-5`.
- OpenAI primary: `gpt-4.1`; fast tier: `gpt-4.1-mini`.
- Anthropic requests use block-array `system` with `cache_control: ephemeral` on the stable agent prefix. Per-turn evidence is appended after an `EVIDENCE_CACHE_BOUNDARY` sentinel (defined in `providers.llm.base`) which the client splits so the stable prefix stays cacheable across turns.

## Security & gate invariants

- **Adult-room gate.** Any session carrying `discussion_style=sexy`, `experience_mode=after_dark`, `desire_lens`, `adult_intensity`, or `erotic_focus` must include `adult_confirmed=true` in `POST /v1/sessions/start`. The PATCH preferences route enforces the same rule on updates. The DiscussionSession row stores `adult_confirmed` + `adult_confirmed_at`. `DiscussionEngine.is_adult` requires both the preference signal AND the server-side confirmation before the after-dark agent runs. See migration `004_add_adult_confirmed.py`.
- **Citation grading.** Only `match_type` in `{"exact", "normalized"}` is allowed to set `verified=True`. Word-set overlap (previously `"fuzzy"`) now surfaces as `match_type="near_match"`, `verified=False`, with a `match_score` alongside. Threshold is 0.95; anything below is rejected outright.
- **Admin router** is wrapped in a `require_admin` dependency that calls `hmac.compare_digest` on `X-Admin-Token` against `ADMIN_TOKEN`.
- **Upload path** streams uploads in 1MB chunks with a running byte cap so oversized requests are rejected before buffering.
- **Docker.** The API image runs as a non-root `api` user. The default compose file binds Postgres (5432) and Redis (6379) to 127.0.0.1 only.

## Current Frontend Behavior

Routes:
- `/` - Library home (static, code-split)
- `/books/[bookId]` - Session setup (dynamic)
- `/books/[bookId]/sessions/[sessionId]` - Discussion (dynamic)

The frontend currently supports:

- library browsing with Continue Reading, search, extension filters
- session setup with mode, style, time budget, reader goal, experience mode, room autonomy
- reading-slice selection with section previews
- discussion streaming with multi-agent turns
- click-to-highlight citation linking (reader panel scrolls to cited span)
- text mode and conversational audio mode with sentence-level TTS
- mobile-responsive sidebar with slide-in overlay
- toast notifications for all user actions (sonner)
- a dedicated adult-session setup path with 18+ gating
- after-dark CSS class (`.after-dark`) that transforms density/warmth/friction

Design system:
- Typography: Literata (serif headlines), Inter (body), Space Grotesk (labels)
- Color tokens: warm stone base, amber primary, rose after-dark
- Agent tokens: Sam=amber, Ellis=teal, Kit=rose, AfterDark=fuchsia
- Citation tokens: exact=emerald, normalized=amber, fuzzy=yellow, unverified=red
- After-dark mode: density transformation (deeper bg, softer contrast, slower animations, warmer glass blur)

## Current Verification State

Current observed backend test run in this workspace:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest apps/api/tests -q -p no:typeguard`
- result: `485 passed, 1 warning`

Observed warning:

- `PytestConfigWarning: Unknown config option: asyncio_mode`

Frontend checks that have passed in this workspace:

- `npx tsc --noEmit` in `apps/web`
- `npm run build` in `apps/web`

## Prioritized Next Tasks (from adversary review, 2026-03-30)

Architecture:
1. ~~Break God components~~ — IN PROGRESS: `useAudioPlayback` hook extracted, `useDiscussionSession` in progress
2. ~~Extract shared types~~ — DONE: `apps/web/types/api.ts` created
3. ~~Use motion library~~ — DONE: page.tsx, book setup, session opener use motion/react
4. ~~Session opener transition~~ — DONE: cinematic room-opening with staggered cast intro

Product:
5. ~~Thumbs up/down~~ — DONE: backend PATCH endpoint + frontend inline buttons + alembic migration
6. ~~Kill stat cards~~ — DONE: replaced with time-of-day aware greeting
7. ~~Agent visual distinction~~ — DONE: role-specific border colors + "counterpoint"/"close read" badges
8. ~~Time-of-day awareness~~ — DONE: morning/afternoon/evening/late-night greetings
9. ~~Public domain seeder~~ — DONE: `scripts/seed_public_domain.py` (5 Gutenberg novels)

Operations:
10. Cost dashboard: aggregate token usage from metadata_json, expose via /admin/costs
11. Prompt registry: versioned store, log which version produced which response
12. Nightly eval pipeline: automated citation accuracy + agent distinctiveness scoring

Research integration (from arXiv/innovation sprint):
13. Voxtral TTS provider: self-hosted, 70ms latency, beats ElevenLabs, voice cloning
14. ModernBERT reranker swap: drop-in for BAAI/bge-reranker-v2-m3
15. SC-RAG pre-generation evidence gate: quality-check retrieval before agent generation

## Known Caveats

- The test warning about `asyncio_mode` is still present.
- `apps/web/components/discussion-stage.tsx` still contains a client-side fallback sentence extractor for backward compatibility, even though server-driven `sentence_ready` events now exist.
- `apps/web/components/discussion-stage.tsx` is 1534 lines and needs decomposition (see task #1 above).
- `motion` package is installed but not yet imported in any component.
- `SessionRecap` component is created but not yet wired into any view.
- `VoiceRoster` and `CitationCard` components are created but discussion-stage still uses inline implementations.
- `pytest-of-evela/` is present in the worktree as a test artifact.

## Current Product Notes

The current product already includes these higher-level features:

- multi-agent discussion with Sam, Ellis, and Kit
- persistent book memory
- sentence-level streamed audio
- local audiobook pairing
- adult-session preferences such as `desire_lens`, `adult_intensity`, and `erotic_focus`

These are current code facts, not planned features.

## If You Need To Change Code

Use the live code as the source of truth for implementation details.

Preferred verification sequence:

1. Inspect the relevant backend route, engine, or frontend component
2. Make the smallest coherent code change
3. Run the most targeted test or typecheck that covers the change
4. Expand to broader checks only if the change touches shared behavior

When a doc conflicts with code, the code wins.
