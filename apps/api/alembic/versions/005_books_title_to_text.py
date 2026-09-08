"""Widen Book.title/author/filename from VARCHAR(500) to TEXT.

Revision ID: 005
Revises: 004
Create Date: 2026-05-12

Real ebook filenames in the wild routinely exceed 500 characters when the
whole tagline / series / author / volume number / publisher is packed into
one name. PostgreSQL truncates and fails the INSERT, so ingestion silently
loses those volumes. TEXT removes the cap with no measurable cost in PG.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("books", "title", type_=sa.Text(), existing_nullable=False)
    op.alter_column("books", "author", type_=sa.Text(), existing_nullable=True)
    op.alter_column("books", "filename", type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    # Truncate to 500 chars on downgrade to avoid the same overflow error
    # when re-narrowing the column.
    op.execute("UPDATE books SET title = LEFT(title, 500)")
    op.execute("UPDATE books SET author = LEFT(author, 500) WHERE author IS NOT NULL")
    op.execute("UPDATE books SET filename = LEFT(filename, 500)")
    op.alter_column("books", "title", type_=sa.String(length=500), existing_nullable=False)
    op.alter_column("books", "author", type_=sa.String(length=500), existing_nullable=True)
    op.alter_column("books", "filename", type_=sa.String(length=500), existing_nullable=False)
