"""social eyes: ads and social_cache

Revision ID: 3f6b2c1d9a7e
Revises: e5b79c74a1a4
Create Date: 2026-10-09 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3f6b2c1d9a7e"
down_revision: Union[str, Sequence[str], None] = "e5b79c74a1a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ad_archive_id", sa.String(length=40), nullable=False),
        sa.Column("page_name", sa.String(length=200), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("ad_text", sa.Text(), nullable=False),
        sa.Column("platforms", JSON, nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_foreign", sa.Boolean(), nullable=True),
        sa.Column("sector_slug", sa.String(length=80), nullable=True),
        sa.Column("gap_id", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", JSON, nullable=True),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ad_archive_id"),
    )
    op.create_table(
        "social_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("query_key", sa.String(length=320), nullable=False),
        sa.Column("items", JSON, nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "query_key", name="ux_social_cache_query"),
    )


def downgrade() -> None:
    op.drop_table("social_cache")
    op.drop_table("ads")
