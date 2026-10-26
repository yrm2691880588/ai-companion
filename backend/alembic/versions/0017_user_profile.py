"""用户身份表。

Revision ID: 0017_user_profile
Revises: 0016_analytics
Create Date: 2026-10-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_user_profile"
down_revision: str | None = "0016_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("nickname", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("identity", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("city", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("background", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "companion_user_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "companion_id",
            sa.BigInteger(),
            sa.ForeignKey("companions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nickname", sa.String(length=20), nullable=True),
        sa.Column("identity", sa.String(length=60), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=8), nullable=True),
        sa.Column("city", sa.String(length=40), nullable=True),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "companion_id", name="uq_companion_user_profile"),
    )


def downgrade() -> None:
    op.drop_table("companion_user_profiles")
    op.drop_table("user_profiles")
