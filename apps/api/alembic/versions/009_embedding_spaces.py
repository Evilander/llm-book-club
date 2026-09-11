"""Track vector provenance and index reader thoughts without replacing books."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("embedding_spaces"):
        op.create_table("embedding_spaces", sa.Column("id", sa.String(64), primary_key=True), sa.Column("spec_json", sa.JSON(), nullable=False))
    for table in ("chunks", "messages"):
        columns = {c["name"] for c in inspector.get_columns(table)}
        if table == "messages" and "embedding" not in columns:
            op.add_column(table, sa.Column("embedding", Vector(3072), nullable=True))
        if "embedding_space" not in columns:
            op.add_column(table, sa.Column("embedding_space", sa.String(64), sa.ForeignKey("embedding_spaces.id"), nullable=True))
    if "ix_chunks_book_space" not in {i["name"] for i in inspector.get_indexes("chunks")}:
        op.create_index("ix_chunks_book_space", "chunks", ["book_id", "embedding_space"])
    # Intentionally leave old vectors unlabelled. A model cannot be inferred
    # from its dimension. Reindexing preserves chunks, citations, and positions.


def downgrade() -> None:
    pass  # Older versions ignore these additive fields; preserve reader data.
