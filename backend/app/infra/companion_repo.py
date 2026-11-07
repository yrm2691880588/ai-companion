"""伴侣与人设版本：Postgres 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.device import current_device_id
from app.core.ids import new_ulid
from app.domain.companions import CompanionRecord, PersonaVersionRecord
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
        self,
        user_id: str,
        name: str,
        persona: Persona,
        compiled_prompt: str,
        derived_from: int | None = None,
        ulid: str | None = None,
    ) -> CompanionRecord:
        async with self._session_factory() as session:
            companion = Companion(
                user_id=user_id,
                name=name,
                current_version=1,
                memory_enabled=True,
                ulid=ulid or new_ulid(),
                origin_device_id=current_device_id(),
                derived_from=derived_from,
            )
            session.add(companion)
            await session.flush()
            session.add(
                CompanionPersona(
                    companion_id=companion.id,
                    version=1,
                    persona=persona.model_dump(mode="json"),
                    compiled_prompt=compiled_prompt,
                    ulid=new_ulid(),
                    origin_device_id=current_device_id(),
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
                avatar=companion.avatar,
                ulid=companion.ulid,
                derived_from=companion.derived_from,
                voice_id=companion.voice_id,
                voice_params=companion.voice_params,
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
                    ulid=new_ulid(),
                    origin_device_id=current_device_id(),
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
                avatar=companion.avatar,
                ulid=companion.ulid,
                derived_from=companion.derived_from,
                voice_id=companion.voice_id,
                voice_params=companion.voice_params,
                created_at=companion.created_at or datetime.now(UTC),
                updated_at=companion.updated_at,
            )

    async def list_versions(
        self, user_id: str, companion_id: int
    ) -> list[PersonaVersionRecord]:
        """按版本号倒序返回历史人设（最新的在前）。"""
        async with self._session_factory() as session:
            owned = (
                await session.execute(
                    select(Companion.id).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if owned is None:
                return []
            rows = (
                await session.execute(
                    select(CompanionPersona)
                    .where(CompanionPersona.companion_id == companion_id)
                    .order_by(CompanionPersona.version.desc())
                )
            ).scalars().all()
        return [
            PersonaVersionRecord(
                version=row.version,
                persona=Persona.model_validate(row.persona),
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_version(
        self, user_id: str, companion_id: int, version: int
    ) -> PersonaVersionRecord | None:
        async with self._session_factory() as session:
            owned = (
                await session.execute(
                    select(Companion.id).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if owned is None:
                return None
            row = (
                await session.execute(
                    select(CompanionPersona).where(
                        CompanionPersona.companion_id == companion_id,
                        CompanionPersona.version == version,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return PersonaVersionRecord(
            version=row.version,
            persona=Persona.model_validate(row.persona),
            created_at=row.created_at,
        )

    async def prune_versions(self, user_id: str, companion_id: int, keep: int) -> int:
        """只保留最近的 keep 个版本，返回删掉的行数。

        为什么需要：每次保存都新增一行，改得多了会无限增长。
        删的永远是最旧的版本。
        """
        if keep < 1:
            return 0
        async with self._session_factory() as session:
            owned = (
                await session.execute(
                    select(Companion.id).where(
                        Companion.id == companion_id,
                        Companion.user_id == user_id,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if owned is None:
                return 0
            versions = (
                await session.execute(
                    select(CompanionPersona.version)
                    .where(CompanionPersona.companion_id == companion_id)
                    .order_by(CompanionPersona.version.desc())
                )
            ).scalars().all()
            if len(versions) <= keep:
                return 0
            stale = versions[keep:]
            await session.execute(
                delete(CompanionPersona).where(
                    CompanionPersona.companion_id == companion_id,
                    CompanionPersona.version.in_(stale),
                )
            )
            await session.commit()
        return len(stale)

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

    async def find_by_ulid(self, user_id: str, ulid: str) -> CompanionRecord | None:
        """按 ULID 查伴侣，用于导入去重；空值直接返回 None。"""
        cleaned = (ulid or "").strip()
        if not cleaned:
            return None
        async with self._session_factory() as session:
            companion = (
                await session.execute(
                    select(Companion).where(
                        Companion.user_id == user_id,
                        Companion.ulid == cleaned,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if companion is None:
                return None
            row = (
                await session.execute(
                    select(CompanionPersona)
                    .where(
                        CompanionPersona.companion_id == companion.id,
                        CompanionPersona.version == companion.current_version,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return _to_record(companion, row)

    async def set_avatar(
        self, user_id: str, companion_id: int, avatar: str | None
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
            companion.avatar = avatar
            companion.updated_at = datetime.now(UTC)
            await session.commit()
            return await self.get(user_id, companion_id)

    async def set_voice(
        self, user_id: str, companion_id: int, voice_id: str | None
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
            companion.voice_id = voice_id
            companion.updated_at = datetime.now(UTC)
            await session.commit()
            return await self.get(user_id, companion_id)


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
        avatar=companion.avatar,
        ulid=companion.ulid,
        derived_from=companion.derived_from,
        voice_id=companion.voice_id,
        voice_params=companion.voice_params,
        created_at=companion.created_at,
        updated_at=companion.updated_at,
    )
