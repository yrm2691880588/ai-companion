"""给同步范围内的表补充跨端标识。

Revision ID: 0021_sync_fields
Revises: 0020_voice
Create Date: 2026-10-27

补充的表：
- conversation_summaries（摘要）
- roleplay_runs（演练）
- user_profiles（通用身份）
- companion_user_profiles（伴侣级身份）

存量数据的 ULID 用 Python 生成（与 app.core.ids.new_ulid 完全一致），
避免在 SQL 里做 128 位位运算。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.ids import new_ulid

revision: str = "0021_sync_fields"
down_revision: str | None = "0020_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "conversation_summaries",
    "roleplay_runs",
    "user_profiles",
    "companion_user_profiles",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        op.add_column(table, sa.Column("ulid", sa.String(length=26), nullable=True))
        op.add_column(table, sa.Column("origin_device_id", sa.String(length=64), nullable=True))

        # 回填：逐行生成 ULID，设备标识先统一标成本机
        ids = [row[0] for row in bind.execute(sa.text(f'SELECT id FROM "{table}"'))]
        for row_id in ids:
            bind.execute(
                sa.text(
                    f'UPDATE "{table}" SET ulid = :ulid, origin_device_id = :device WHERE id = :id'
                ),
                {"ulid": new_ulid(), "device": "local", "id": row_id},
            )

        op.alter_column(table, "ulid", nullable=False)
        op.create_index(f"ix_{table}_ulid", table, ["ulid"], unique=True)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_ulid", table_name=table)
        op.drop_column(table, "origin_device_id")
        op.drop_column(table, "ulid")
