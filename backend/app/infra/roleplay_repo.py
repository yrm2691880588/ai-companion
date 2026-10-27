"""演练与安全：Postgres 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_ulid
from app.domain.roleplay import RunRecord, Scenario
from app.models.roleplay import RoleplayRun, RoleplayScenario, SafetyEvent


class SqlScenarioRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, category: str | None = None) -> list[Scenario]:
        async with self._session_factory() as session:
            stmt = select(RoleplayScenario).where(RoleplayScenario.enabled.is_(True))
            if category:
                stmt = stmt.where(RoleplayScenario.category == category)
            rows = (await session.execute(stmt.order_by(RoleplayScenario.key))).scalars().all()
        return [_to_scenario(row) for row in rows]

    async def get(self, key: str) -> Scenario | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(RoleplayScenario).where(RoleplayScenario.key == key))
            ).scalar_one_or_none()
        return _to_scenario(row) if row is not None else None

    async def sync(self, scenarios: tuple[Scenario, ...]) -> int:
        async with self._session_factory() as session:
            existing = {
                row.key: row
                for row in (await session.execute(select(RoleplayScenario))).scalars().all()
            }
            for item in scenarios:
                payload = {
                    "title": item.title,
                    "category": item.category,
                    "role": item.role,
                    "goal": item.goal,
                    "difficulty": item.difficulty,
                    "max_turns": item.max_turns,
                    "opening": item.opening,
                    "tips": item.tips,
                    "enabled": True,
                }
                row = existing.get(item.key)
                if row is None:
                    session.add(RoleplayScenario(key=item.key, **payload))
                else:
                    for field_name, value in payload.items():
                        setattr(row, field_name, value)
            await session.commit()
        return len(scenarios)


class SqlRunRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self, user_id: str, companion_id: int, scenario_key: str, session_id: int, max_turns: int
    ) -> RunRecord:
        async with self._session_factory() as session:
            row = RoleplayRun(
                ulid=new_ulid(),
                origin_device_id="local",
                user_id=user_id,
                companion_id=companion_id,
                scenario_key=scenario_key,
                session_id=session_id,
                max_turns=max_turns,
            )
            session.add(row)
            await session.commit()
            return _to_run(row)

    async def get(self, user_id: str, run_id: int) -> RunRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RoleplayRun).where(
                        RoleplayRun.id == run_id, RoleplayRun.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
        return _to_run(row) if row is not None else None

    async def increment_turns(self, user_id: str, run_id: int) -> int:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RoleplayRun).where(
                        RoleplayRun.id == run_id, RoleplayRun.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return 0
            row.turns_played += 1
            if row.turns_played >= row.max_turns and row.status == "active":
                row.status = "max_reached"
            await session.commit()
            return row.turns_played

    async def finish(self, user_id: str, run_id: int, review: dict[str, object]) -> None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RoleplayRun).where(
                        RoleplayRun.id == run_id, RoleplayRun.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.review = review
            row.status = "finished"
            row.finished_at = datetime.now(UTC)
            await session.commit()


class SqlSafetyRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(
        self, user_id: str, session_id: int | None, level: str, keywords: list[str]
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                SafetyEvent(
                    user_id=user_id,
                    session_id=session_id,
                    level=level,
                    keywords=",".join(keywords)[:200],
                )
            )
            await session.commit()


def _to_scenario(row: RoleplayScenario) -> Scenario:
    return Scenario(
        key=row.key,
        title=row.title,
        category=row.category,
        role=row.role,
        goal=row.goal,
        difficulty=row.difficulty,
        max_turns=row.max_turns,
        opening=row.opening,
        tips=row.tips,
    )


def _to_run(row: RoleplayRun) -> RunRecord:
    return RunRecord(
        id=row.id,
        ulid=row.ulid,
        user_id=row.user_id,
        companion_id=row.companion_id,
        scenario_key=row.scenario_key,
        session_id=row.session_id,
        status=row.status,
        max_turns=row.max_turns,
        turns_played=row.turns_played,
        review=row.review,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )
