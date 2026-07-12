from sqlalchemy.orm import Session

from ..db import ReaderProfile
from ..settings import settings


DEFAULT_READER_PREFERENCES = {
    "theme": "paper",
    "flow": "paginated",
    "fontSize": 18,
    "lineHeight": 1.72,
    "maxWidth": 680,
}


def reader_profile_id() -> str:
    return (settings.reader_profile_id.strip() or "local")[:100]


def get_or_create_reader_profile(db: Session) -> ReaderProfile:
    profile = db.get(ReaderProfile, reader_profile_id())
    if profile:
        return profile
    profile = ReaderProfile(
        id=reader_profile_id(),
        preferences_json=dict(DEFAULT_READER_PREFERENCES),
    )
    db.add(profile)
    db.flush()
    return profile
