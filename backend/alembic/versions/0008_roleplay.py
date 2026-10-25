"""演练场景、运行记录与安全事件表。

Revision ID: 0008_roleplay
Revises: 0007_summaries
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_roleplay"
down_revision: str | None = "0007_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "roleplay_scenarios",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=60), nullable=False),
        sa.Column("goal", sa.String(length=200), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("opening", sa.Text(), nullable=False),
        sa.Column("tips", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "roleplay_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "companion_id",
            sa.BigInteger(),
            sa.ForeignKey("companions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scenario_key", sa.String(length=64), nullable=False),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("turns_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_roleplay_runs_user", "roleplay_runs", ["user_id", "created_at"])

    op.create_table(
        "safety_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("keywords", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_safety_events_user", "safety_events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_safety_events_user", table_name="safety_events")
    op.drop_table("safety_events")
    op.drop_index("ix_roleplay_runs_user", table_name="roleplay_runs")
    op.drop_table("roleplay_runs")
    op.drop_table("roleplay_scenarios")
