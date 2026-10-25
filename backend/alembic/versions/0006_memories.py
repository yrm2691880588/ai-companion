"""长期记忆表与伴侣的记忆开关。

Revision ID: 0006_memories
Revises: 0005_chat
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_memories"
down_revision: str | None = "0005_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companions",
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "companion_id",
            sa.BigInteger(),
            sa.ForeignKey("companions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, server_default="0.70"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source_session_id", sa.BigInteger(), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memories_user_companion_status", "memories", ["user_id", "companion_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_companion_status", table_name="memories")
    op.drop_table("memories")
    op.drop_column("companions", "memory_enabled")
