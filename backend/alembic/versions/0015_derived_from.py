"""伴侣衍生来源。

Revision ID: 0015_derived_from
Revises: 0014_sync_fields
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_derived_from"
down_revision: str | None = "0014_sync_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companions", sa.Column("derived_from", sa.BigInteger(), nullable=True))
    op.create_index("ix_companions_derived_from", "companions", ["derived_from"])


def downgrade() -> None:
    op.drop_index("ix_companions_derived_from", table_name="companions")
    op.drop_column("companions", "derived_from")
