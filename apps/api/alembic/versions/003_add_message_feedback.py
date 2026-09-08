"""Add feedback column to messages table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("feedback", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "feedback")
