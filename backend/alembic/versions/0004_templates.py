"""官方模板表。

Revision ID: 0004_templates
Revises: 0003_companions
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_templates"
down_revision: str | None = "0003_companions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "companion_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("tagline", sa.String(length=120), nullable=False),
        sa.Column("persona", JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("companion_templates")
