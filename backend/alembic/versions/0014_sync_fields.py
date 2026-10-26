"""同步预留字段与 outbox。

Revision ID: 0014_sync_fields
Revises: 0013_avatar
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_sync_fields"
down_revision: str | None = "0013_avatar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
TABLES = ("companions", "companion_personas", "sessions", "messages", "memories")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("ulid", sa.String(length=26), nullable=True))
        op.add_column(table, sa.Column("origin_device_id", sa.String(length=64), nullable=True))
    op.add_column("messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # 回填：用 Python 生成 ULID，避免依赖扩展
    from app.core.ids import new_ulid

    conn = op.get_bind()
    for table in TABLES:
        rows = conn.execute(sa.text(f'SELECT id FROM "{table}"')).fetchall()
        for (row_id,) in rows:
            conn.execute(
                sa.text(f'UPDATE "{table}" SET ulid = :ulid WHERE id = :id'),
                {"ulid": new_ulid(), "id": row_id},
            )
        conn.execute(
            sa.text(f'UPDATE "{table}" SET origin_device_id = :device WHERE origin_device_id IS NULL'),
            {"device": "local"},
        )

    for table in TABLES:
        op.alter_column(table, "ulid", existing_type=sa.String(length=26), nullable=False)
        op.create_index(f"ix_{table}_ulid", table, ["ulid"], unique=True)

    op.create_table(
        "sync_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_ulid", sa.String(length=26), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sync_outbox_created", "sync_outbox", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_outbox_created", table_name="sync_outbox")
    op.drop_table("sync_outbox")
    for table in TABLES:
        op.drop_index(f"ix_{table}_ulid", table_name=table)
        op.drop_column(table, "ulid")
        op.drop_column(table, "origin_device_id")
    op.drop_column("messages", "deleted_at")
