"""Add server-side 18+ gate columns to discussion_sessions.

Revision ID: 004
Revises: 003
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discussion_sessions",
        sa.Column(
            "adult_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "discussion_sessions",
        sa.Column("adult_confirmed_at", sa.DateTime(), nullable=True),
    )
    # Drop the server_default once the column is populated — new rows get the
    # column value from the ORM default (False) or an explicit set.
    op.alter_column("discussion_sessions", "adult_confirmed", server_default=None)


def downgrade() -> None:
    op.drop_column("discussion_sessions", "adult_confirmed_at")
    op.drop_column("discussion_sessions", "adult_confirmed")
