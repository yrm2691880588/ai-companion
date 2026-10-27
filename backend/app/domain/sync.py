"""同步 outbox：把本地写操作记成可推送的事件。

设计要点（ADR-0009 / 0010）：
- 只追加，不改不删；
- 每次本地写入后落一条事件，payload 是推送所需的最小快照；
- 同一事务内写入，避免“数据写了但事件丢了”；
- 没有同步服务时这张表只增长不消费，因此需要清理策略（由后续同步功能负责）。

注意：本表不参与业务读取，业务语义仍以各领域表为准。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncOutbox


@dataclass(slots=True)
class OutboxEvent:
    entity_type: str
    entity_ulid: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class OutboxRepository(Protocol):
    async def append(self, event: OutboxEvent) -> None: ...

    async def list_since(self, offset: int, limit: int) -> list[OutboxEvent]: ...


def record(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_ulid: str,
    operation: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """在调用方的事务里追加一条事件（不 commit，由调用方统一提交）。"""
    if not entity_ulid:
        return
    session.add(
        SyncOutbox(
            entity_type=entity_type,
            entity_ulid=entity_ulid,
            operation=operation,
            payload=payload or {},
        )
    )


class SqlOutboxRepository:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def append(self, event: OutboxEvent) -> None:
        async with self._session_factory() as session:
            record(
                session,
                entity_type=event.entity_type,
                entity_ulid=event.entity_ulid,
                operation=event.operation,
                payload=event.payload,
            )
            await session.commit()

    async def list_since(self, offset: int, limit: int) -> list[OutboxEvent]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(SyncOutbox)
                        .order_by(SyncOutbox.id)
                        .offset(max(offset, 0))
                        .limit(min(max(limit, 1), 500))
                    )
                )
                .scalars()
                .all()
            )
        return [
            OutboxEvent(
                entity_type=row.entity_type,
                entity_ulid=row.entity_ulid,
                operation=row.operation,
                payload=dict(row.payload or {}),
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def prune(self, *, keep: int = 5000, max_age_days: int = 30) -> int:
        """清理 outbox：只保留最近 keep 条。

        没有同步服务时这张表会一直增长，必须设上界（AGENTS §5）。
        """
        keep = max(keep, 100)
        async with self._session_factory() as session:
            total = (
                await session.execute(select(func.count()).select_from(SyncOutbox))
            ).scalar_one()
            if total <= keep:
                return 0
            cutoff_id = (
                await session.execute(
                    select(SyncOutbox.id).order_by(SyncOutbox.id.desc()).offset(keep - 1).limit(1)
                )
            ).scalar_one_or_none()
            if cutoff_id is None:
                return 0
            result = await session.execute(delete(SyncOutbox).where(SyncOutbox.id < cutoff_id))
            await session.commit()
            return result.rowcount or 0

    async def stats(self) -> dict[str, int]:
        async with self._session_factory() as session:
            total = (
                await session.execute(select(func.count()).select_from(SyncOutbox))
            ).scalar_one()
        return {"pending": int(total)}


class InMemoryOutboxRepository:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def append(self, event: OutboxEvent) -> None:
        self.events.append(event)

    async def list_since(self, offset: int, limit: int) -> list[OutboxEvent]:
        return self.events[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 500)]

    async def prune(self, *, keep: int = 5000, max_age_days: int = 30) -> int:
        keep = max(keep, 100)
        if len(self.events) <= keep:
            return 0
        removed = len(self.events) - keep
        self.events = self.events[-keep:]
        return removed

    async def stats(self) -> dict[str, int]:
        return {"pending": len(self.events)}
