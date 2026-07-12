"""Add synced local-audiobook listening state.

Revision ID: 006
Revises: 005
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audiobook_listening_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("audiobook_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.Column("current_track_id", sa.String(length=64), nullable=False),
        sa.Column("track_index", sa.Integer(), nullable=False),
        sa.Column("position_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("playback_rate", sa.Float(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["reader_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "audiobook_id",
            name="uq_audiobook_listening_state_profile_audiobook",
        ),
    )
    op.create_index(
        "ix_audiobook_listening_states_recent",
        "audiobook_listening_states",
        ["profile_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audiobook_listening_states_recent",
        table_name="audiobook_listening_states",
    )
    op.drop_table("audiobook_listening_states")
