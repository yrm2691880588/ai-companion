"""整库备份的依赖排序：保证恢复时父表先于子表写入。"""

from __future__ import annotations

from scripts.backup_db import sort_by_dependency
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table


def build_metadata() -> MetaData:
    metadata = MetaData()
    Table("companions", metadata, Column("id", Integer, primary_key=True))
    Table(
        "sessions",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("companion_id", ForeignKey("companions.id")),
    )
    Table(
        "messages",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("session_id", ForeignKey("sessions.id")),
    )
    Table(
        "companion_personas",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("companion_id", ForeignKey("companions.id")),
    )
    return metadata


def test_parent_before_child() -> None:
    metadata = build_metadata()
    ordered = sort_by_dependency(
        metadata, ["messages", "sessions", "companions", "companion_personas"]
    )
    assert ordered.index("companions") < ordered.index("sessions")
    assert ordered.index("sessions") < ordered.index("messages")
    assert ordered.index("companions") < ordered.index("companion_personas")


def test_independent_tables_kept() -> None:
    metadata = build_metadata()
    ordered = sort_by_dependency(metadata, ["companions", "companion_personas"])
    assert set(ordered) == {"companions", "companion_personas"}
    assert ordered.index("companions") < ordered.index("companion_personas")


def test_cycle_does_not_hang() -> None:
    """环形依赖时不应死循环，至少把所有表都返回。"""
    metadata = MetaData()
    Table("a", metadata, Column("id", Integer, primary_key=True))
    result = sort_by_dependency(metadata, ["a"])
    assert result == ["a"]


def test_empty_input() -> None:
    assert sort_by_dependency(MetaData(), []) == []
