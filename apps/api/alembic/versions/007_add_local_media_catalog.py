"""Add the persistent local-media catalog.

Revision ID: 007
Revises: 006
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_media_catalogs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("root_key", sa.String(length=64), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("extension_signature", sa.Text(), nullable=False),
        sa.Column("content_signature", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("active_generation", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("scan_duration_ms", sa.Integer(), nullable=False),
        sa.Column("scan_job_id", sa.String(length=100), nullable=True),
        sa.Column("scan_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("scan_started_at", sa.DateTime(), nullable=True),
        sa.Column("scan_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kind", "root_key", name="uq_local_media_catalog_kind_root"
        ),
    )
    op.create_index(
        "ix_local_media_catalog_status",
        "local_media_catalogs",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_table(
        "local_media_catalog_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("catalog_id", sa.String(length=36), nullable=False),
        sa.Column("media_id", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=1000), nullable=False),
        sa.Column("extension", sa.String(length=20), nullable=False),
        sa.Column("format_family", sa.String(length=20), nullable=False),
        sa.Column("reader_kind", sa.String(length=20), nullable=True),
        sa.Column("can_discuss", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_at", sa.String(length=50), nullable=False),
        sa.Column("title_guess", sa.String(length=1000), nullable=False),
        sa.Column("parent_folder", sa.String(length=1000), nullable=True),
        sa.Column("seen_generation", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_id"], ["local_media_catalogs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_id", "media_id", name="uq_local_media_catalog_item_media"
        ),
        sa.UniqueConstraint(
            "catalog_id", "relative_path", name="uq_local_media_catalog_item_path"
        ),
    )
    op.create_index(
        "ix_local_media_catalog_items_available_title",
        "local_media_catalog_items",
        ["catalog_id", "is_available", "title_guess"],
        unique=False,
    )
    op.create_index(
        "ix_local_media_catalog_items_generation",
        "local_media_catalog_items",
        ["catalog_id", "seen_generation"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_local_media_catalog_items_generation",
        table_name="local_media_catalog_items",
    )
    op.drop_index(
        "ix_local_media_catalog_items_available_title",
        table_name="local_media_catalog_items",
    )
    op.drop_table("local_media_catalog_items")
    op.drop_index(
        "ix_local_media_catalog_status", table_name="local_media_catalogs"
    )
    op.drop_table("local_media_catalogs")
