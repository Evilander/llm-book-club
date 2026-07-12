"""Add server-backed reader profiles, positions, and annotations.

Revision ID: 005
Revises: 004
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reader_profiles",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "publication_reading_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("extension", sa.String(length=20), nullable=False),
        sa.Column("reader_kind", sa.String(length=20), nullable=False),
        sa.Column("can_discuss", sa.Boolean(), nullable=False),
        sa.Column("book_id", sa.String(length=36), nullable=True),
        sa.Column("ingest_status", sa.String(length=30), nullable=True),
        sa.Column("fraction", sa.Float(), nullable=False),
        sa.Column("chapter", sa.String(length=500), nullable=True),
        sa.Column("page", sa.String(length=100), nullable=True),
        sa.Column("location_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["reader_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "publication_id",
            name="uq_publication_reading_state_profile_publication",
        ),
    )
    op.create_index(
        "ix_publication_reading_states_recent",
        "publication_reading_states",
        ["profile_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "reader_annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reading_state_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("fraction", sa.Float(), nullable=False),
        sa.Column("chapter", sa.String(length=500), nullable=True),
        sa.Column("page", sa.String(length=100), nullable=True),
        sa.Column("target_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["reading_state_id"],
            ["publication_reading_states.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reader_annotations_state_deleted",
        "reader_annotations",
        ["reading_state_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reader_annotations_state_deleted", table_name="reader_annotations"
    )
    op.drop_table("reader_annotations")
    op.drop_index(
        "ix_publication_reading_states_recent",
        table_name="publication_reading_states",
    )
    op.drop_table("publication_reading_states")
    op.drop_table("reader_profiles")
