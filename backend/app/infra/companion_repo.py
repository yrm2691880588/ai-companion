"""伴侣与人设版本：Postgres 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.companions import CompanionRecord
from app.domain.persona import Persona
from app.models.companions import Companion, CompanionPersona


class SqlCompanionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def count(self, user_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Companion)
                .where(Companion.user_id == user_id, Companion.deleted_at.is_(None))
            )
            return int(result.scalar_one())

    async def create(
        self, user_id: str, name: str, persona: Persona, compiled_prompt: str
    ) -> CompanionRecord:
        async with self._session_factory() as session:
            companion = Companion(
                user_id=user_id, name=name, current_version=1, memory_enabled=True
            )
            session.add(companion)
            await session.flush()
            session.add(
                CompanionPersona(
                    companion_id=companion.id,
                    version=1,
                    persona=persona.model_dump(mode="json"),
                    compiled_prompt=compiled_prompt,
                )
            )
            await session.commit()
            return CompanionRecord(
                id=companion.id,
                user_id=user_id,
                name=name,
                current_version=1,
                persona=persona,
                compiled_prompt=compiled_prompt,
                memory_enabled=True,
                created_at=companion.created_at or datetime.now(UTC),
                updated_at=companion.updated_at or datetime.now(UTC),
            )

    async def list(self, user_id: str) -> list[CompanionRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Companion, CompanionPersona)
                    .join(
                        CompanionPersona,
                        (CompanionPersona.companion_id == Companion.id)
                        & (CompanionPersona.version == Companion.current_version),
                    )
                    .where(Companion.user_id == user_id, Companion.deleted_at.is_(None))
                    .order_by(Companion.created_at.desc())
                )
            ).all()
        return [_to_record(companion, persona) for companion, persona in rows]

    async def get(self, user_id: str, companion_id: int) -> CompanionRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Companion, CompanionPersona)
                    .join(
                        CompanionPersona,
                        (CompanionPersona.companion_id == Companion.id)
                        & (CompanionPersona.version == Companion.current_version),
                    )
                    .where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).first()
        if row is None:
            return None
        return _to_record(row[0], row[1])

    async def add_version(
        self, user_id: str, companion_id: int, persona: Persona, compiled_prompt: str
    ) -> CompanionRecord | None:
        async with self._session_factory() as session:
            companion = (
                await session.execute(
                    select(Companion).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if companion is None:
                return None
            version = companion.current_version + 1
            session.add(
                CompanionPersona(
                    companion_id=companion.id,
                    version=version,
                    persona=persona.model_dump(mode="json"),
                    compiled_prompt=compiled_prompt,
                )
            )
            companion.current_version = version
            companion.name = persona.name
            companion.updated_at = datetime.now(UTC)
            await session.commit()
            return CompanionRecord(
                id=companion.id,
                user_id=user_id,
                name=companion.name,
                current_version=version,
                persona=persona,
                compiled_prompt=compiled_prompt,
                memory_enabled=companion.memory_enabled,
                created_at=companion.created_at or datetime.now(UTC),
                updated_at=companion.updated_at,
            )

    async def soft_delete(self, user_id: str, companion_id: int) -> bool:
        async with self._session_factory() as session:
            companion = (
                await session.execute(
                    select(Companion).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if companion is None:
                return False
            companion.status = "deleted"
            companion.deleted_at = datetime.now(UTC)
            await session.commit()
            return True

    async def set_memory_enabled(self, user_id: str, companion_id: int, enabled: bool) -> bool:
        async with self._session_factory() as session:
            companion = (
                await session.execute(
                    select(Companion).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if companion is None:
                return False
            companion.memory_enabled = enabled
            await session.commit()
            return True


def _to_record(companion: Companion, persona_row: CompanionPersona) -> CompanionRecord:
    persona = Persona.model_validate(persona_row.persona)
    return CompanionRecord(
        id=companion.id,
        user_id=companion.user_id,
        name=companion.name,
        current_version=companion.current_version,
        persona=persona,
        compiled_prompt=persona_row.compiled_prompt,
        memory_enabled=companion.memory_enabled,
        created_at=companion.created_at,
        updated_at=companion.updated_at,
    )
