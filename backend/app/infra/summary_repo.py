"""会话摘要的存储接口与实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat import SessionSummary


@dataclass(slots=True)
class SummaryRecord:
    session_id: int
    summary: str
    covered_seq: int
    updated_at: datetime


class SummaryRepository(Protocol):
    async def get(self, session_id: int) -> SummaryRecord | None: ...

    async def upsert(self, session_id: int, summary: str, covered_seq: int) -> SummaryRecord: ...


class InMemorySummaryRepository:
    def __init__(self) -> None:
        self._items: dict[int, SummaryRecord] = {}

    async def get(self, session_id: int) -> SummaryRecord | None:
        return self._items.get(session_id)

    async def upsert(self, session_id: int, summary: str, covered_seq: int) -> SummaryRecord:
        record = SummaryRecord(
            session_id=session_id,
            summary=summary,
            covered_seq=covered_seq,
            updated_at=datetime.now(UTC),
        )
        self._items[session_id] = record
        return record


class SqlSummaryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, session_id: int) -> SummaryRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(SessionSummary).where(SessionSummary.session_id == session_id)
                )
            ).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    async def upsert(self, session_id: int, summary: str, covered_seq: int) -> SummaryRecord:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(SessionSummary).where(SessionSummary.session_id == session_id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = SessionSummary(
                    session_id=session_id, summary=summary, covered_seq=covered_seq
                )
                session.add(row)
            else:
                row.summary = summary
                row.covered_seq = covered_seq
                row.updated_at = datetime.now(UTC)
            await session.commit()
            return _to_record(row)


def _to_record(row: SessionSummary) -> SummaryRecord:
    return SummaryRecord(
        session_id=row.session_id,
        summary=row.summary,
        covered_seq=row.covered_seq,
        updated_at=row.updated_at,
    )
