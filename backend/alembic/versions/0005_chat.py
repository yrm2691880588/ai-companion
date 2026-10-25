"""会话与消息表。

Revision ID: 0005_chat
Revises: 0004_templates
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_chat"
down_revision: str | None = "0004_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "companion_id",
            sa.BigInteger(),
            sa.ForeignKey("companions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sessions_user_companion", "sessions", ["user_id", "companion_id", "created_at"]
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),
    )
    op.create_index("ix_messages_session_seq", "messages", ["session_id", "seq"])
    op.create_index("ix_messages_client_request", "messages", ["client_request_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_client_request", table_name="messages")
    op.drop_index("ix_messages_session_seq", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_sessions_user_companion", table_name="sessions")
    op.drop_table("sessions")
