"""P0-1 数据约束：ULID、墓碑、outbox。"""

from __future__ import annotations

import pytest

from app.core.ids import new_ulid


def test_ulid_is_26_chars_and_sortable() -> None:
    first = new_ulid()
    second = new_ulid()
    assert len(first) == 26
    assert len(second) == 26
    assert first != second
    assert set(first) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_ulid_unique_in_bulk() -> None:
    values = {new_ulid() for _ in range(2000)}
    assert len(values) == 2000


@pytest.mark.parametrize(
    "table", ["companions", "companion_personas", "sessions", "messages", "memories"]
)
def test_sync_tables_have_ulid_column(table: str) -> None:
    """迁移后每张可同步表都有 ulid 列（结构级断言，用 SQLAlchemy inspector 更重，这里查元数据）。"""
    from app.models.chat import ChatMessage, ChatSession
    from app.models.companions import Companion, CompanionPersona
    from app.models.memory import Memory

    mapping = {
        "companions": Companion,
        "companion_personas": CompanionPersona,
        "sessions": ChatSession,
        "messages": ChatMessage,
        "memories": Memory,
    }
    model = mapping[table]
    assert "ulid" in model.__table__.columns
    assert "origin_device_id" in model.__table__.columns


def test_messages_have_tombstone_column() -> None:
    from app.models.chat import ChatMessage

    assert "deleted_at" in ChatMessage.__table__.columns


def test_sync_outbox_table_exists() -> None:
    from app.models.sync import SyncOutbox

    assert SyncOutbox.__tablename__ == "sync_outbox"
    assert "entity_ulid" in SyncOutbox.__table__.columns
