"""埋点表。

Revision ID: 0016_analytics
Revises: 0015_derived_from
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_analytics"
down_revision: str | None = "0015_derived_from"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_analytics_events_name_created", "analytics_events", ["name", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_name_created", table_name="analytics_events")
    op.drop_table("analytics_events")
