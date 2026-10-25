"""llm_calls 增加模型标识列，并允许供应商/模型的外键 id 为空。

Revision ID: 0002_llm_calls_model_key
Revises: 0001_model_layer
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_llm_calls_model_key"
down_revision: str | None = "0001_model_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("provider_key", sa.String(length=64), nullable=True))
    op.add_column("llm_calls", sa.Column("model_key", sa.String(length=200), nullable=True))
    op.alter_column("llm_calls", "provider_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("llm_calls", "model_profile_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_index("ix_llm_calls_model_key_time", "llm_calls", ["model_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_model_key_time", table_name="llm_calls")
    op.alter_column("llm_calls", "model_profile_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("llm_calls", "provider_id", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("llm_calls", "model_key")
    op.drop_column("llm_calls", "provider_key")
