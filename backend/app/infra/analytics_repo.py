"""埋点：写入与按天聚合。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.analytics import AnalyticsEvent

ALLOWED_EVENTS = frozenset(
    {
        "app_open",
        "create_start",
        "create_success",
        "first_message",
        "first_reply",
        "message_action",
        "persona_save",
        "error",
    }
)


class InMemoryAnalyticsRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def record(
        self,
        user_id: str,
        name: str,
        *,
        session_id: int | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.events.append(
            {
                "user_id": user_id,
                "name": name,
                "session_id": session_id,
                "duration_ms": duration_ms,
                "error_code": error_code,
            }
        )

    async def summary(self, days: int = 7) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for event in self.events:
            name = str(event["name"])
            counts[name] = counts.get(name, 0) + 1
        return [{"day": "today", "name": name, "count": count} for name, count in counts.items()]


class SqlAnalyticsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        user_id: str,
        name: str,
        *,
        session_id: int | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                AnalyticsEvent(
                    user_id=user_id,
                    name=name,
                    session_id=session_id,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
            )
            await session.commit()

    async def summary(self, days: int = 7) -> list[dict[str, object]]:
        since = datetime.now() - timedelta(days=days)
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        func.date(AnalyticsEvent.created_at).label("day"),
                        AnalyticsEvent.name,
                        func.count().label("count"),
                    )
                    .where(AnalyticsEvent.created_at >= since)
                    .group_by("day", AnalyticsEvent.name)
                    .order_by("day", AnalyticsEvent.name)
                )
            ).all()
        return [{"day": str(row.day), "name": row.name, "count": int(row.count)} for row in rows]
