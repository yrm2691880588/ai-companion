"""管理员角色、系统设置与管理员审计。

Revision ID: 0012_admin
Revises: 0011_deletion
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_admin"
down_revision: str | None = "0011_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
    )
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before", JSONB, nullable=True),
        sa.Column("after", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_created", "admin_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_created", table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_table("system_settings")
    op.drop_column("accounts", "role")
