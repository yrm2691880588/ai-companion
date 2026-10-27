"""长期记忆：Postgres 实现。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.device import current_device_id
from app.core.ids import new_ulid
from app.domain.memory import MemoryRecord, normalize_content
from app.models.memory import Memory


class SqlMemoryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str,
        content: str,
        confidence: float,
        quote: str | None,
        source_session_id: int | None,
        source_message_id: int | None,
    ) -> MemoryRecord:
        async with self._session_factory() as session:
            row = Memory(
                user_id=user_id,
                companion_id=companion_id,
                type=type,
                content=content,
                confidence=confidence,
                quote=quote,
                source_session_id=source_session_id,
                source_message_id=source_message_id,
                ulid=new_ulid(),
                origin_device_id=current_device_id(),
            )
            session.add(row)
            await session.commit()
            return _to_record(row)

    async def list(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[MemoryRecord]:
        async with self._session_factory() as session:
            stmt = select(Memory).where(
                Memory.user_id == user_id,
                Memory.companion_id == companion_id,
                Memory.status == status,
            )
            if type:
                stmt = stmt.where(Memory.type == type)
            rows = (
                (await session.execute(stmt.order_by(Memory.created_at.desc()).limit(limit)))
                .scalars()
                .all()
            )
        return [_to_record(row) for row in rows]

    async def get(self, user_id: str, memory_id: int) -> MemoryRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
                )
            ).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    async def soft_delete(self, user_id: str, memory_id: int) -> bool:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.status = "deleted"
            row.deleted_at = datetime.now(UTC)
            await session.commit()
            return True

    async def find_duplicate(
        self, user_id: str, companion_id: int, type: str, content: str
    ) -> MemoryRecord | None:
        candidates = await self.list(user_id, companion_id, type=type, limit=200)
        target = normalize_content(content)
        return next(
            (item for item in candidates if normalize_content(item.content) == target), None
        )

    async def mark_used(self, memory_ids: Sequence[int]) -> None:
        if not memory_ids:
            return
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Memory).where(Memory.id.in_(list(memory_ids)))))
                .scalars()
                .all()
            )
            now = datetime.now(UTC)
            for row in rows:
                row.last_used_at = now
            await session.commit()


def _to_record(row: Memory) -> MemoryRecord:
    return MemoryRecord(
        id=row.id,
        ulid=row.ulid,
        user_id=row.user_id,
        companion_id=row.companion_id,
        type=row.type,
        content=row.content,
        confidence=float(row.confidence),
        status=row.status,
        source_session_id=row.source_session_id,
        source_message_id=row.source_message_id,
        quote=row.quote,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )
