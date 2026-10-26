"""用户身份：Postgres 实现。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.user_profile import (
    CompanionUserProfileRecord,
    UserProfileRecord,
)
from app.models.user_profile import CompanionUserProfile, UserProfile


class SqlUserProfileRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, user_id: str) -> UserProfileRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            ).scalar_one_or_none()
        if row is None:
            return None
        return UserProfileRecord(
            nickname=row.nickname,
            identity=row.identity,
            age=row.age,
            gender=row.gender,
            city=row.city,
            background=row.background,
        )

    async def upsert(self, user_id: str, profile: UserProfileRecord) -> UserProfileRecord:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            ).scalar_one_or_none()
            if row is None:
                row = UserProfile(user_id=user_id)
                session.add(row)
            row.nickname = profile.nickname
            row.identity = profile.identity
            row.age = profile.age
            row.gender = profile.gender
            row.city = profile.city
            row.background = profile.background
            await session.commit()
        return profile

    async def get_for_companion(
        self, user_id: str, companion_id: int
    ) -> CompanionUserProfileRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(CompanionUserProfile).where(
                        CompanionUserProfile.user_id == user_id,
                        CompanionUserProfile.companion_id == companion_id,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return CompanionUserProfileRecord(
            companion_id=row.companion_id,
            nickname=row.nickname,
            identity=row.identity,
            age=row.age,
            gender=row.gender,
            city=row.city,
            background=row.background,
        )

    async def upsert_for_companion(
        self, user_id: str, companion_id: int, profile: CompanionUserProfileRecord
    ) -> CompanionUserProfileRecord:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(CompanionUserProfile).where(
                        CompanionUserProfile.user_id == user_id,
                        CompanionUserProfile.companion_id == companion_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = CompanionUserProfile(user_id=user_id, companion_id=companion_id)
                session.add(row)
            row.nickname = profile.nickname
            row.identity = profile.identity
            row.age = profile.age
            row.gender = profile.gender
            row.city = profile.city
            row.background = profile.background
            await session.commit()
        return profile
