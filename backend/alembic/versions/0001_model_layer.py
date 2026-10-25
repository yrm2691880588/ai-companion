"""模型层初始表：供应商、模型档案、定价、任务路由、调用流水。

Revision ID: 0001_model_layer
Revises:
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_model_layer"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "model_providers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("key_hint", sa.String(length=32), nullable=True),
        sa.Column("allow_private", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_model_providers_owner", "model_providers", ["owner_user_id"])

    op.create_table(
        "model_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "provider_id",
            sa.BigInteger(),
            sa.ForeignKey("model_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("max_output", sa.Integer(), nullable=False),
        sa.Column("supports", JSONB, nullable=False, server_default="[]"),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("capability_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("pricing_known", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pricing_version_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "model_name", name="uq_profile_provider_model"),
    )

    op.create_table(
        "pricing_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "model_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("model_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("input_hit", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("input_miss", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("output", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("time_band", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("effective_from", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_pricing_profile_effective", "pricing_versions", ["model_profile_id", "effective_from"]
    )

    op.create_table(
        "model_routes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("chain", JSONB, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("owner_user_id", "task", name="uq_route_owner_task"),
    )
    op.create_index("ix_model_routes_owner", "model_routes", ["owner_user_id"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("model_profile_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("first_token_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_llm_calls_user_time", "llm_calls", ["user_id", "created_at"])
    op.create_index("ix_llm_calls_model_time", "llm_calls", ["model_profile_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_model_time", table_name="llm_calls")
    op.drop_index("ix_llm_calls_user_time", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_model_routes_owner", table_name="model_routes")
    op.drop_table("model_routes")
    op.drop_index("ix_pricing_profile_effective", table_name="pricing_versions")
    op.drop_table("pricing_versions")
    op.drop_table("model_profiles")
    op.drop_index("ix_model_providers_owner", table_name="model_providers")
    op.drop_table("model_providers")
