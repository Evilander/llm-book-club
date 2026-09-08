"""Widen Section.title from VARCHAR(500) to TEXT.

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

Chapter / section titles routinely exceed 500 characters when the
extractor lifts copyright + back-matter "About the Author" paragraphs
out of the file. PostgreSQL truncates and the entire book INSERT fails.
TEXT removes the cap.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("sections", "title", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.execute("UPDATE sections SET title = LEFT(title, 500) WHERE title IS NOT NULL")
    op.alter_column("sections", "title", type_=sa.String(length=500), existing_nullable=True)
