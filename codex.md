# codex.md — LLM Book Club Handoff for Codex

This file is the complete handoff document for OpenAI's Codex coding model.
It describes the architecture, what works, what's next, and how to run everything.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    apps/web (Next.js)                        │
│  page.tsx → BookShelf → SessionSetup → DiscussionStage      │
│  SSE streaming ← /v1/sessions/{id}/stream                   │
│  TTS audio   ← /v1/tts/stream (sentence-by-sentence)       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│                   apps/api (FastAPI)                          │
│                                                              │
│  Routers:                                                    │
│    ingest.py    — Upload, /v1/books (enriched), /v1/ingest   │
│    library.py   — /v1/library/local, explore, audiobooks     │
│    sessions.py  — Start/stream/message discussion sessions   │
│    tts.py       — /v1/tts/synthesize, /stream, /agent-voices │
│    memory.py    — Book memory CRUD, session memory rollups   │
│    health.py    — Health check                               │
│                                                              │
│  Discussion Engine:                                          │
│    engine.py         — Orchestration, SSE streaming          │
│    agents.py         — FacilitatorAgent, CloseReaderAgent,   │
│                        SkepticAgent (Sam, Ellis, Kit)        │
│    prompts.py        — Personalities + adult overlays        │
│    sentence_splitter — Streaming sentence detection for TTS  │
│    memory_prompts.py — Memory-aware prompt construction      │
│    metrics.py        — CitationMetrics, TurnMetrics          │
│    token_budget.py   — History truncation, evidence trimming │
│                                                              │
│  Retrieval:                                                  │
│    search.py    — Hybrid: pgvector + FTS + RRF + reranking   │
│    filters.py   — Evidence block builder, suspicious flagging│
│    selector.py  — Session slice selection                    │
│    cache.py     — Embedding cache                            │
│                                                              │
│  Providers (pluggable):                                      │
│    llm/      — OpenAI, Anthropic, Gemini, Grok, local        │
│    embeddings/ — OpenAI, Gemini, local                       │
│    tts/      — VibeVoice, ElevenLabs, OpenAI                 │
│    reranker/ — Cohere, local                                 │
│                                                              │
│  Ingestion:                                                  │
│    extractor.py          — PDF/EPUB/TXT text extraction      │
│    chunker.py            — Section → chunk splitting         │
│    intelligent_chunker.py — LLM-assisted chunking            │
│    pipeline.py           — Full ingestion pipeline           │
│                                                              │
│  Services:                                                   │
│    media_library.py — Local filesystem book/audiobook scan   │
│                                                              │
│  DB: PostgreSQL + pgvector (SQLAlchemy ORM)                  │
│  Queue: Redis + RQ (async ingestion)                         │
└──────────────────────────────────────────────────────────────┘
```

## File Tree (key files only)

```
llm-book/
├── codex.md                    ← YOU ARE HERE
├── CLAUDE.md                   ← Detailed product + engineering manual
├── AGENTS.md                   ← Multi-model coordination guidance
├── docker-compose.yml          ← Postgres (pgvector), Redis, API, Web
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py                     # FastAPI app factory
│   │   │   ├── settings.py                 # Pydantic settings (all env vars)
│   │   │   ├── db/
│   │   │   │   ├── models.py               # ORM models (Book, Section, Chunk, DiscussionSession, Message, BookMemory, etc.)
│   │   │   │   ├── engine.py               # DB engine setup
│   │   │   │   └── init_db.py              # Table creation
│   │   │   ├── discussion/
│   │   │   │   ├── engine.py               # DiscussionEngine — orchestrates multi-agent turns + SSE streaming
│   │   │   │   ├── agents.py               # BaseAgent, FacilitatorAgent, CloseReaderAgent, SkepticAgent
│   │   │   │   ├── prompts.py              # AGENT_PERSONALITIES, ADULT_AGENT_OVERLAYS, DISCUSSION_MODES
│   │   │   │   ├── sentence_splitter.py    # SentenceSplitter — streaming sentence detection for TTS
│   │   │   │   ├── memory_prompts.py       # Memory-aware prompt templates
│   │   │   │   ├── metrics.py              # CitationMetrics, TurnMetrics, StageMetrics
│   │   │   │   └── token_budget.py         # History truncation, evidence trimming
│   │   │   ├── retrieval/
│   │   │   │   ├── search.py               # hybrid_search (vector + FTS + RRF + reranking)
│   │   │   │   ├── filters.py              # Evidence block builder
│   │   │   │   ├── selector.py             # Session slice selection
│   │   │   │   └── cache.py               # Embedding cache
│   │   │   ├── ingest/
│   │   │   │   ├── extractor.py            # PDF/EPUB/TXT extraction
│   │   │   │   ├── chunker.py             # Basic chunking
│   │   │   │   ├── intelligent_chunker.py  # LLM-assisted chunking
│   │   │   │   └── pipeline.py            # Full ingestion pipeline
│   │   │   ├── providers/
│   │   │   │   ├── llm/                    # LLM clients (openai, anthropic, gemini, grok, local)
│   │   │   │   ├── embeddings/             # Embedding clients (openai, gemini, local)
│   │   │   │   ├── tts/                    # TTS clients (vibevoice, elevenlabs, openai)
│   │   │   │   └── reranker/               # Reranking clients (cohere, local)
│   │   │   ├── routers/
│   │   │   │   ├── ingest.py               # Upload + /v1/books (enriched)
│   │   │   │   ├── library.py              # Local library browse + audiobook matching
│   │   │   │   ├── sessions.py             # Discussion session CRUD + streaming
│   │   │   │   ├── tts.py                  # TTS synthesis + streaming + agent-voices
│   │   │   │   ├── memory.py               # Book memory endpoints
│   │   │   │   └── health.py               # Health check
│   │   │   └── services/
│   │   │       └── media_library.py        # Local FS book/audiobook scanning
│   │   ├── alembic/
│   │   │   └── versions/
│   │   │       ├── 001_add_hnsw_index_and_fts.py
│   │   │       └── 002_add_session_preferences.py
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_agents.py              # Agent tests + adult mode overlay tests
│   │   │   ├── test_sentence_splitter.py   # 19 sentence splitter tests
│   │   │   ├── test_eval_retrieval.py      # Retrieval quality benchmarks (precision, recall, MRR)
│   │   │   ├── test_eval_citations.py      # Citation verification regression tests
│   │   │   ├── test_eval_search_quality.py # Hybrid vs. single-source comparisons
│   │   │   ├── fixtures/
│   │   │   │   └── eval_gold.py            # Gold corpus: "The Glass Botanist" / "The Voss Inheritance"
│   │   │   └── ... (14 test files, 464 tests total)
│   │   ├── .env.example
│   │   ├── requirements.txt
│   │   └── pytest.ini
│   │
│   └── web/
│       ├── app/
│       │   ├── layout.tsx
│       │   └── page.tsx                    # Main view controller (library → setup → discussion)
│       ├── components/
│       │   ├── book-shelf.tsx              # Library browse (Continue Reading, Start New, local browse)
│       │   ├── session-setup.tsx           # Session config (mode, preferences, adult settings)
│       │   ├── discussion-stage.tsx        # Discussion UI (SSE, sentence audio, citations)
│       │   ├── voice-input.tsx             # Speech-to-text input
│       │   ├── error-boundary.tsx
│       │   └── ui/                         # shadcn/ui components
│       ├── lib/
│       │   └── utils.ts                    # API_BASE, cn(), formatters
│       ├── package.json
│       └── tailwind.config.ts
│
└── infra/                                  # (placeholder for future infra configs)
```

## What Works End-to-End

### 1. Book Ingestion
```
Upload PDF/EPUB/TXT → Extract text → Detect sections → Chunk → Embed → Store in Postgres
```
- Works via upload or local filesystem ingest
- Async via Redis + RQ worker
- Sections detected automatically; chunks stored with char offsets and embeddings

### 2. Library Browse
```
Open app → See "Continue Reading" (books with sessions) → See "Start New" → Browse local library
```
- Enriched book cards: section count, session count, last session date, audiobook badge
- Search, filter by extension, paginated local library
- Drag-and-drop upload

### 3. Session Setup
```
Select book → Choose mode + preferences → Start session → Select reading slice
```
- Modes: conversation, deep_dive, big_picture, first_time, poetry, nonfiction
- Preferences: discussion style, vibes, voice profile, reader goal
- Adult mode: desire lens, adult intensity, erotic focus (behind 18+ gate)
- Section explorer with preview text and audiobook pairing

### 4. Multi-Agent Discussion
```
User message → MARS classifier → Facilitator (always) → Close Reader (if needed) → Skeptic (if needed)
```
- MARS adaptive selection: cheap LLM call decides which agents respond
- Streaming via SSE with hardened protocol (event_id, turn_id, sequence, reconnect support)
- Structured JSON citations verified server-side with span alignment
- Citation repair when >50% invalid
- Turn metrics with TTFT tracking and budget checks

### 5. Voice Mode (Sentence-Level TTS)
```
LLM streams text → SentenceSplitter detects boundaries → sentence_ready SSE events → Frontend fires TTS per-sentence
```
- Each agent has a distinct voice: Sam=nova, Ellis=shimmer, Kit=echo
- Turn-taking indicator: "Sam is speaking..."
- Interrupt on user input: audio stops immediately
- Backward-compatible: frontend auto-detects sentence_ready support

### 6. Adult/Erotic Mode
```
Session prefs include desire_lens/adult_intensity → adult_mode=True → Agent overlays activate
```
- Sam → Seductive Host: tracks erotic tension, names the body, paces like seduction
- Ellis → Desire Anatomist: traces desire in sentence mechanics, reads clothing/gesture
- Kit → Desire Interrogator: challenges whose pleasure is centered, asks about gaze/consent
- All overlays additive: base personality + security firewall + citations preserved

### 7. Book Memory
```
Per-book memory: themes, characters, key moments, connections → Inform later sessions
```
- Memory context injected into agent prompts
- Phase guidance based on reading progress

## How to Run

### Docker (recommended)
```bash
# Copy and configure env
cp apps/api/.env.example apps/api/.env
# Edit .env with your API keys (at minimum: OPENAI_API_KEY or another LLM provider)

# Start everything
docker compose up --build

# Frontend: http://localhost:3000
# API: http://localhost:8000
# API docs: http://localhost:8000/docs
```

### Local Development
```bash
# Terminal 1: Database + Redis
docker compose up db redis

# Terminal 2: API
cd apps/api
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # edit with your keys
python -c "from app.db.init_db import init_db; init_db()"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 3: Worker (for ingestion)
cd apps/api
python run_worker.py

# Terminal 4: Frontend
cd apps/web
npm install
npm run dev
```

### Run Tests
```bash
cd apps/api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q -p no:typeguard
# Expected: 464 passed
```

## Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (needs pgvector) |
| `REDIS_URL` | Yes | — | Redis URL for job queue |
| `LLM_PROVIDER` | No | `openai` | `openai\|claude\|gemini\|grok\|local` |
| `OPENAI_API_KEY` | If using OpenAI | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | If using Claude | — | Anthropic API key |
| `GEMINI_API_KEY` | If using Gemini | — | Google AI API key |
| `GROK_API_KEY` | If using Grok | — | xAI API key |
| `EMBEDDINGS_PROVIDER` | No | `openai` | `openai\|gemini\|local` |
| `TTS_PROVIDER` | No | `vibevoice` | `vibevoice\|elevenlabs\|openai` |
| `TTS_BASE_URL` | If vibevoice | — | OpenAI-compatible TTS proxy URL |
| `ELEVENLABS_API_KEY` | If elevenlabs | — | ElevenLabs API key |
| `BOOKS_DIR` | No | — | Local books directory path |
| `AUDIOBOOKS_DIR` | No | — | Local audiobooks directory path |
| `RERANKER_PROVIDER` | No | `none` | `none\|cohere\|local` |
| `COHERE_API_KEY` | If cohere reranker | — | Cohere API key |

## How to Add Providers

### LLM Provider
1. Create `apps/api/app/providers/llm/yourprovider.py` implementing `LLMClient` protocol
2. Add to `apps/api/app/providers/llm/factory.py`
3. Add env vars to `apps/api/app/settings.py`

### Embeddings Provider
1. Create `apps/api/app/providers/embeddings/yourprovider.py` implementing `EmbeddingsClient`
2. Add to `apps/api/app/providers/embeddings/factory.py`

### TTS Provider
1. Create `apps/api/app/providers/tts/yourprovider.py` implementing `TTSClient` (synthesize + stream)
2. Add to `apps/api/app/providers/tts/factory.py`

## Next Tasks (Prioritized)

### P0 — Operational Readiness
1. **End-to-end smoke test with a real book** — Upload a PDF, verify ingestion completes, start a session, send messages, verify citations map to real text, test voice mode
2. **Error recovery** — SSE reconnection on network drop, ingestion retry on worker crash, graceful TTS fallback to text
3. **Alembic migrations in Docker** — Ensure `alembic upgrade head` runs on container startup

### P1 — Product Quality
4. **Session continuity** — Resume a previous session (currently each session starts fresh)
5. **Reading progress tracking** — Mark sections as read, show progress on book cards
6. **"Read Tonight" recommendations** — Use session history + time-of-day + reading patterns to suggest books
7. **Marginalia / Notes** — Highlights and notes pinned to text spans, visible during discussion
8. **Export** — Session transcript export as markdown

### P2 — Voice & Audio
9. **Audiobook sync** — Play local audiobook in sync with the reading slice being discussed
10. **Voice input improvements** — Whisper-based STT with continuous listening mode
11. **Agent speaking choreography** — Configurable pause between agents, overlapping speech prevention

### P3 — Quality & Scale
12. **Retrieval eval dashboard** — Surface eval metrics (precision, recall, MRR) in a dev panel
13. **Citation quality monitoring** — Alert when verification rate drops below threshold
14. **Multi-user support** — User accounts, per-user book memory, session isolation

## Known Bugs / Tech Debt

- `typing_extensions` version conflict causes `typeguard` plugin to fail — tests require `-p no:typeguard` flag
- `text_search` tsvector column may not exist on fresh DBs without running Alembic migration 001 — FTS gracefully degrades to empty results
- Client-side `extractSpeakableSegments()` in `discussion-stage.tsx` is now redundant (replaced by server-side `sentence_ready` events) but kept for backward compat — can be removed after confirming all backends are updated
- Some `print()` calls remain in TTS error handling — should use `logging`
- The `pytest-of-evela/` temp directory with test fixtures leaks into the repo — add to `.gitignore`

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Hybrid retrieval (vector + FTS + RRF) | FTS catches names/entities, vector catches themes. RRF merges without parameter tuning |
| MARS adaptive agent selection | Cheap classifier saves 1-2 LLM calls per turn when only facilitator is needed |
| Structured JSON citations | Server-side verification requires structured output, not regex parsing |
| Sentence-level TTS pipelining | First audio in 2-4s instead of 10-20s. Each sentence → separate TTS request |
| Adult overlays as additive layers | Base personality preserved. Security firewall preserved. Easy to disable |
| Per-agent TTS voices | Users can distinguish agents by voice in audio-only mode |
| Gold eval corpus as dataclasses | Type-safe, IDE-navigable, no external fixture files to manage |
