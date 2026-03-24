# LLM Book Club

LLM Book Club is a multi-agent reading companion for people who want better conversations with books, not thinner summaries. Drop in a PDF, EPUB, or TXT file, pick a slice to discuss, and let Sam, Ellis, and Kit turn the text into a live, grounded conversation with citations.

Built for local-first reading workflows, the app combines fast ingestion, hybrid retrieval, streaming responses, and long-term book memory so discussions can keep their thread across sessions.

## Features

- Multi-agent discussion with three distinct AI voices:
  Sam is the enthusiastic guide, Ellis is the close reader, and Kit is the devil's advocate.
- Upload or browse local PDF, EPUB, and TXT books from your filesystem.
- Open the active reading slice in a built-in reader panel while the discussion is running.
- Switch between text mode and conversational audio mode with streaming TTS playback.
- Pair an ingested ebook with likely local audiobook matches from a configured audiobook folder.
- Real-time streaming responses over SSE for a live discussion feel.
- Hybrid retrieval with pgvector, PostgreSQL full-text search, Reciprocal Rank Fusion, and optional reranking.
- Citation-grounded responses tied back to the source text.
- Pluggable LLM providers including OpenAI, Anthropic, Gemini, Grok, and local/Ollama-compatible endpoints.
- Pluggable TTS providers including VibeVoice, ElevenLabs, and OpenAI.
- Redis + RQ background ingestion so large books process asynchronously.
- Persistent book memory that tracks themes, characters, and key moments across sessions.

## Quick Start

### Prerequisites

- Docker
- An API key for at least one hosted model provider:
  `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

### 1. Copy environment files

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.local.example apps/web/.env.local
```

PowerShell:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

### 2. Add your API key

Edit `apps/api/.env` and set at least one provider key:

```env
OPENAI_API_KEY=your-key-here
# or
ANTHROPIC_API_KEY=your-key-here
```

### 3. Start the stack

```bash
docker compose up --build
```

### 4. Open the app

Visit [http://localhost:3000](http://localhost:3000).

The API will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Development Setup

If you want to run without Docker, start PostgreSQL 16 with `pgvector` and Redis locally first.

Backend:

```bash
cd apps/api
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Worker:

```bash
cd apps/api
python run_worker.py
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

## Architecture

- `apps/web`: Next.js 15 + TypeScript + Tailwind + shadcn/ui frontend for library browsing, session setup, chat, and audio playback.
- `apps/api`: FastAPI + SQLAlchemy + Pydantic backend for ingestion, sessions, retrieval, citations, memory, and provider orchestration.
- PostgreSQL 16 + `pgvector`: stores books, chunks, embeddings, citations, and persistent reading memory.
- Redis + RQ: handles async ingestion and other background work.
- Provider layer: swaps LLM, embedding, reranker, and TTS backends without changing the application flow.

## Configuration

Most settings live in `apps/api/.env`.

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`: hosted LLM provider credentials.
- `LLM_PROVIDER`: `openai`, `claude`, `gemini`, `grok`, or `local`.
- `LOCAL_LLM_BASE_URL`: OpenAI-compatible local endpoint, such as Ollama.
- `EMBEDDINGS_PROVIDER`: `openai`, `gemini`, or `local`.
- `OPENAI_EMBEDDINGS_MODEL`, `LOCAL_EMBEDDINGS_BASE_URL`, `LOCAL_EMBEDDINGS_MODEL`: embedding configuration.
- `RERANKER_PROVIDER`: `none`, `cohere`, or `local`.
- `COHERE_API_KEY`, `RERANKER_MODEL`, `LOCAL_RERANKER_MODEL`: reranking configuration.
- `TTS_PROVIDER`: `vibevoice`, `elevenlabs`, or `openai`.
- `TTS_BASE_URL`: OpenAI-compatible TTS endpoint. For the bundled VibeVoice service, use `http://localhost:8880/v1`.
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TTS_MODEL`: TTS settings.
- `BOOKS_DIR`: local directory exposed for filesystem book browsing.
- `AUDIOBOOKS_DIR`: optional local audiobook directory used for matching likely companion audio files.
- `DATABASE_URL`, `REDIS_URL`: infrastructure connections.
- `CORS_ORIGINS`, `MAX_UPLOAD_MB`: app-level behavior.

Provider note:

- This repo currently authenticates hosted model providers with server-side API credentials.
- OpenAI and Anthropic end-user OAuth is not wired in here because their current API flows for this stack still use API-key style server authentication rather than drop-in user OAuth sessions.

Frontend configuration lives in `apps/web/.env.local`:

- `NEXT_PUBLIC_API_BASE_URL`: API base URL for the web app.

## Stack

- Frontend: Next.js 15, TypeScript, Tailwind CSS, shadcn/ui
- Backend: FastAPI, SQLAlchemy, Pydantic
- Database: PostgreSQL 16, pgvector
- Queue: Redis, RQ

## License

MIT
