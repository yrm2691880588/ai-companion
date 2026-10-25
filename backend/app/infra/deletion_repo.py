"""彻底删除：Postgres 实现（依赖外键级联）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFound
from app.domain.deletion import DeletionJobRecord
from app.models.chat import ChatMessage, ChatSession, SessionSummary
from app.models.companions import Companion, CompanionPersona
from app.models.deletion import DeletionJob
from app.models.memory import Memory
from app.models.roleplay import RoleplayRun, SafetyEvent


class SqlDeletionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(self, user_id: str, companion_id: int) -> DeletionJobRecord:
        async with self._session_factory() as session:
            row = DeletionJob(user_id=user_id, companion_id=companion_id)
            session.add(row)
            await session.commit()
            return _to_job(row)

    async def get(self, job_id: int) -> DeletionJobRecord | None:
        async with self._session_factory() as session:
            row = await session.get(DeletionJob, job_id)
        return _to_job(row) if row is not None else None

    async def pending(self, limit: int = 20) -> list[DeletionJobRecord]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DeletionJob)
                        .where(DeletionJob.status == "pending")
                        .order_by(DeletionJob.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [_to_job(row) for row in rows]

    async def mark_done(self, job_id: int, detail: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(DeletionJob, job_id)
            if row is not None:
                row.status = "done"
                row.detail = detail[:1000]
                row.processed_at = datetime.now(UTC)
                await session.commit()

    async def mark_failed(self, job_id: int, detail: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(DeletionJob, job_id)
            if row is not None:
                row.status = "failed"
                row.detail = detail[:1000]
                row.attempts += 1
                row.processed_at = datetime.now(UTC)
                await session.commit()

    async def purge(self, user_id: str, companion_id: int) -> dict[str, int]:
        async with self._session_factory() as session:
            companion = (
                await session.execute(
                    select(Companion).where(
                        Companion.id == companion_id, Companion.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
            if companion is None:
                raise NotFound("伴侣不存在或已删除")

            session_ids = list(
                (
                    await session.execute(
                        select(ChatSession.id).where(ChatSession.companion_id == companion_id)
                    )
                ).scalars()
            )
            counts = {
                "personas": await _count(
                    session, CompanionPersona, CompanionPersona.companion_id == companion_id
                ),
                "sessions": len(session_ids),
                "messages": await _count(
                    session, ChatMessage, ChatMessage.session_id.in_(session_ids)
                )
                if session_ids
                else 0,
                "summaries": await _count(
                    session, SessionSummary, SessionSummary.session_id.in_(session_ids)
                )
                if session_ids
                else 0,
                "memories": await _count(session, Memory, Memory.companion_id == companion_id),
                "roleplay_runs": await _count(
                    session, RoleplayRun, RoleplayRun.companion_id == companion_id
                ),
            }
            if session_ids:
                await session.execute(
                    delete(SafetyEvent).where(SafetyEvent.session_id.in_(session_ids))
                )
            await session.execute(
                delete(Companion).where(Companion.id == companion_id, Companion.user_id == user_id)
            )
            await session.commit()
            return counts


async def _count(session: AsyncSession, model: object, condition: object) -> int:
    result = await session.execute(select(func.count()).select_from(model).where(condition))
    return int(result.scalar_one())


def _to_job(row: DeletionJob) -> DeletionJobRecord:
    return DeletionJobRecord(
        id=row.id,
        user_id=row.user_id,
        companion_id=row.companion_id,
        status=row.status,
        attempts=row.attempts,
        detail=row.detail,
        created_at=row.created_at,
        processed_at=row.processed_at,
    )
