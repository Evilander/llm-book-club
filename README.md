# LLM Book Club

A web application for discussing books with AI companions. Upload a PDF or EPUB, select a reading slice, and engage in structured discussion with a **Facilitator** and **Close Reader** — via text and voice — with citations grounded in the actual text.

![LLM Book Club](https://via.placeholder.com/800x400?text=LLM+Book+Club)

## Features

- **Large book support**: Handles books of any size through chunking and embedding
- **Multi-agent discussion**: Facilitator guides, Close Reader provides textual evidence
- **4 discussion modes**: Guided, Socratic, Poetry, Nonfiction
- **Grounded citations**: Every claim links to specific text passages
- **Voice output**: TTS support via VibeVoice, ElevenLabs, or OpenAI
- **Reading sessions**: Focus on manageable slices with time budgets

## Quick Start

### Prerequisites
- Docker + Docker Compose
- OpenAI API key (for embeddings and LLM)

### Setup

```bash
# 1. Clone and configure
git clone <repo>
cd llm-book

# 2. Copy environment files
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.local.example apps/web/.env.local

# 3. Edit apps/api/.env and add your OpenAI API key:
#    OPENAI_API_KEY=sk-...

# 4. Start all services (includes worker)
docker compose up --build
```

### Access
- **Web UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

## Usage

1. **Upload a book**: Drag and drop a PDF or EPUB file
2. **Wait for processing**: The book will be chunked and embedded (watch the status)
3. **Click the book** when it shows "Ready"
4. **Configure session**: Choose discussion mode and time budget
5. **Start discussing**: The Facilitator will open with questions
6. **Enable voice**: Click "Voice On" to hear agent responses

## Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL 16 + pgvector |
| Queue | Redis + RQ |
| LLM | OpenAI GPT-4o / Claude (configurable) |
| Embeddings | OpenAI text-embedding-3-large |
| TTS | VibeVoice / ElevenLabs / OpenAI |

## Project Structure

```
llm-book/
├── apps/
│   ├── api/          # FastAPI backend
│   └── web/          # Next.js frontend
├── packages/
│   └── shared/       # Shared types
├── docker-compose.yml
├── CLAUDE.md         # Build instructions
├── codex.md          # Technical handoff doc
└── README.md
```

## Configuration

### LLM Provider
Set `LLM_PROVIDER` in `apps/api/.env`:
- `openai` (default) - requires `OPENAI_API_KEY`
- `claude` - requires `ANTHROPIC_API_KEY`

### TTS Provider
Set `TTS_PROVIDER` in `apps/api/.env`:
- `openai` - uses OpenAI TTS
- `vibevoice` - uses VibeVoice (OpenAI-compatible proxy)
- `elevenlabs` - requires `ELEVENLABS_API_KEY`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/ingest` | Upload a book |
| `GET /v1/books` | List all books |
| `POST /v1/sessions/start` | Start a discussion session |
| `POST /v1/sessions/{id}/message` | Send a message |
| `POST /v1/tts/synthesize` | Generate speech |

See full API documentation at http://localhost:8000/docs

## Development

### Local Backend
```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Local Frontend
```bash
cd apps/web
npm install
npm run dev
```

## License

MIT

---

Built with Claude Code
