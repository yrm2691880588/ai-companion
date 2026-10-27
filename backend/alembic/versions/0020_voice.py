"""语音功能表：供应商配置、音色、伴侣音色、用量。

Revision ID: 0020_voice
Revises: 0019_custom_models
Create Date: 2026-10-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_voice"
down_revision: str | None = "0019_custom_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "voice_provider_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "voice_voices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("voice_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("params_schema", JSONB, nullable=True),
        sa.Column("cached_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_key", "voice_id", name="uq_voice_provider_voice"),
    )

    op.add_column("companions", sa.Column("voice_id", sa.String(length=128), nullable=True))
    op.add_column("companions", sa.Column("voice_params", JSONB, nullable=True))

    op.create_table(
        "voice_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("asr_ms", sa.Integer(), nullable=True),
        sa.Column("tts_chars", sa.Integer(), nullable=True),
        sa.Column("cost_cny", sa.Numeric(10, 6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_voice_usage_created", "voice_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_usage_created", table_name="voice_usage")
    op.drop_table("voice_usage")
    op.drop_column("companions", "voice_params")
    op.drop_column("companions", "voice_id")
    op.drop_table("voice_voices")
    op.drop_table("voice_provider_settings")
