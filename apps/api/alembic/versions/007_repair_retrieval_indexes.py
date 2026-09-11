"""Repair missing search objects and use an index that supports 3072 dimensions.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier fresh installations stamped 006 without creating derived objects.
    op.execute("""
        ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    """)
    op.execute("DROP INDEX IF EXISTS idx_chunks_text_search")
    op.execute("CREATE INDEX idx_chunks_text_search ON chunks USING gin(text_search)")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("""
        CREATE INDEX ix_chunks_embedding_hnsw
        ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    # Reading preferences were added to the ORM without a historical migration.
    if not sa.inspect(op.get_bind()).has_table("reading_prefs"):
        op.create_table(
            "reading_prefs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=False),
            sa.Column("theme", sa.String(64), nullable=False),
            sa.Column("font_family", sa.String(64), nullable=False),
            sa.Column("font_size_px", sa.Integer(), nullable=False),
            sa.Column("line_height", sa.Float(), nullable=False),
            sa.Column("measure_ch", sa.Integer(), nullable=False),
            sa.Column("focus_reading", sa.Boolean(), nullable=False),
            sa.Column("focus_reading_intensity", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_reading_prefs_user_id", "reading_prefs", ["user_id"], unique=True)


def downgrade() -> None:
    # These repairs are compatible with 006. Preserve preferences, full-text
    # data, and the working HNSW index when returning to the previous release.
    pass
