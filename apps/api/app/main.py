from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .routers import health, ingest, sessions, tts, memory, library
from .db.init_db import init_db
from .settings import settings
from .rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup
    init_db()
    yield


app = FastAPI(title="LLM Book Club API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Parse CORS origins: use configured value, only allow wildcard if explicitly set
_cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router, prefix="/v1")
app.include_router(sessions.router, prefix="/v1")
app.include_router(tts.router, prefix="/v1")
app.include_router(library.router, prefix="/v1")
app.include_router(memory.router)
