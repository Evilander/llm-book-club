"""The selected companion is explicit and survives API/worker restarts."""
from datetime import datetime

from sqlalchemy.orm import Session

from ..db.models import LibraryConfiguration
from ..settings import settings


def canonical_provider(provider: str) -> str:
    provider = provider.lower().strip()
    return {"claude": "anthropic", "xai": "grok", "google": "gemini"}.get(provider, provider)


def selected_provider(db: Session | None = None) -> str:
    config = db.get(LibraryConfiguration, 1) if db is not None else None
    return canonical_provider(config.llm_provider if config else settings.llm_provider)


def select_provider(db: Session, provider: str) -> str:
    # Concurrent tabs may make the first selection together. An upsert keeps
    # this a single row without losing either transaction to a duplicate key.
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    values = {"id": 1, "llm_provider": canonical_provider(provider), "updated_at": datetime.utcnow()}
    statement = insert(LibraryConfiguration).values(**values)
    db.execute(statement.on_conflict_do_update(index_elements=["id"], set_=values))
    db.commit()
    db.expire_all()
    return values["llm_provider"]
