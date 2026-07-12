"""Use a halfvec expression for the 3,072-dimensional HNSW index.

Revision ID: 008
Revises: 007
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing databases may have an unusable direct-vector index, no index at
    # all because its build failed, or the corrected expression from a fresh
    # migration 001. Rebuilding by name makes every state converge.
    op.execute("ALTER EXTENSION vector UPDATE")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute(
        """
        CREATE INDEX ix_chunks_embedding_hnsw
        ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    # The old direct vector(3072) HNSW definition is invalid on supported
    # pgvector releases. A downgrade safely removes ANN acceleration instead
    # of recreating an index that cannot be built; exact vector search remains.
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
