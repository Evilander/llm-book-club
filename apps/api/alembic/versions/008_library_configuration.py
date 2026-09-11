"""Persist the library's selected conversation provider.

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("library_configuration"):
        op.create_table(
            "library_configuration",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("llm_provider", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_library_configuration_singleton"),
        )


def downgrade() -> None:
    # Older versions ignore this additive table. Preserve the reader's choice.
    pass
