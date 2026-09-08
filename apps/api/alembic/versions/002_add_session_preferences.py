"""Add discussion session preferences_json column.

Revision ID: 002
Revises: 001
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discussion_sessions",
        sa.Column("preferences_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discussion_sessions", "preferences_json")
