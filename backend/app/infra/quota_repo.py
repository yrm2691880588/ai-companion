"""每日用量：Postgres 原子计数。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.quota import DailyUsage


class SqlQuotaRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def consume(self, user_id: str, day: date, limit: int) -> int:
        async with self._session_factory() as session:
            stmt = (
                insert(DailyUsage)
                .values(user_id=user_id, day=day, turns=1)
                .on_conflict_do_update(
                    index_elements=[DailyUsage.user_id, DailyUsage.day],
                    set_={"turns": DailyUsage.turns + 1},
                    where=DailyUsage.turns < limit,
                )
                .returning(DailyUsage.turns)
            )
            turns = (await session.execute(stmt)).scalar_one_or_none()
            if turns is None:
                await session.rollback()
                raise ValueError("quota exceeded")
            await session.commit()
            return int(turns)

    async def get(self, user_id: str, day: date) -> int:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(DailyUsage.turns).where(
                        DailyUsage.user_id == user_id, DailyUsage.day == day
                    )
                )
            ).scalar_one_or_none()
            return int(row or 0)

    async def refund(self, user_id: str, day: date) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(DailyUsage)
                .where(DailyUsage.user_id == user_id, DailyUsage.day == day)
                .values(turns=func.greatest(DailyUsage.turns - 1, 0))
            )
            await session.commit()
