"""Add HNSW index, full-text search column/index, and message metadata column.

Revision ID: 001
Revises: None
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add HNSW index on chunks.embedding for fast approximate nearest-neighbor search.
    #    vector_cosine_ops matches the cosine distance used in retrieval.
    #    m=16 and ef_construction=64 are solid defaults for recall/build-speed tradeoff.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # 2. Add a generated tsvector column for full-text search (BM25-style retrieval).
    #    GENERATED ALWAYS AS ... STORED means Postgres auto-maintains it on INSERT/UPDATE.
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS text_search tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
        """
    )

    # 3. Add GIN index on the tsvector column for fast full-text queries.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_text_search
        ON chunks USING gin(text_search)
        """
    )

    # 4. Add metadata_json column to messages table for extensible per-message metadata
    #    (e.g., token counts, latency, model used, citation verification results).
    op.add_column(
        "messages",
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Reverse in opposite order.
    op.drop_column("messages", "metadata_json")

    op.execute("DROP INDEX IF EXISTS idx_chunks_text_search")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
