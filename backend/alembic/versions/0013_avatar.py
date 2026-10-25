"""伴侣头像（data URL）。

Revision ID: 0013_avatar
Revises: 0012_admin
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_avatar"
down_revision: str | None = "0012_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companions", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companions", "avatar")
