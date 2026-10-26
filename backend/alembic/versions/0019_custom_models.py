"""自定义模型表：保存用户从供应商 /v1/models 导入的模型。

Revision ID: 0019_custom_models
Revises: 0018_provider_settings
Create Date: 2026-10-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_custom_models"
down_revision: str | None = "0018_provider_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_models",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False, server_default="32768"),
        sa.Column("max_output", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_key", "model_name", name="uq_custom_model"),
    )


def downgrade() -> None:
    op.drop_table("custom_models")
