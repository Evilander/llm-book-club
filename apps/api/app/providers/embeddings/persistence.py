"""Persist a model contract once, including under simultaneous first use."""
from dataclasses import asdict
from sqlalchemy.orm import Session

from ...db.models import EmbeddingModel
from .space import EmbeddingSpace


def register_space(db: Session, space: EmbeddingSpace) -> None:
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(EmbeddingModel).values(id=space.id, spec_json=asdict(space)).on_conflict_do_nothing(index_elements=["id"]))
