"""用户身份：通用 + 伴侣级覆盖，编译成提示词片段。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import InvalidInput

MAX_NICKNAME = 20
MAX_IDENTITY = 60
MAX_CITY = 40
MAX_BACKGROUND = 400


@dataclass(slots=True)
class UserProfileRecord:
    nickname: str = ""
    identity: str = ""
    age: int | None = None
    gender: str = ""
    city: str = ""
    background: str = ""


@dataclass(slots=True)
class CompanionUserProfileRecord:
    companion_id: int
    nickname: str | None = None
    identity: str | None = None
    age: int | None = None
    gender: str | None = None
    city: str | None = None
    background: str | None = None


class UserProfileRepository(Protocol):
    async def get(self, user_id: str) -> UserProfileRecord | None: ...

    async def upsert(self, user_id: str, profile: UserProfileRecord) -> UserProfileRecord: ...

    async def get_for_companion(
        self, user_id: str, companion_id: int
    ) -> CompanionUserProfileRecord | None: ...

    async def upsert_for_companion(
        self, user_id: str, companion_id: int, profile: CompanionUserProfileRecord
    ) -> CompanionUserProfileRecord: ...


class InMemoryUserProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[str, UserProfileRecord] = {}
        self.companion_profiles: dict[tuple[str, int], CompanionUserProfileRecord] = {}

    async def get(self, user_id: str) -> UserProfileRecord | None:
        return self.profiles.get(user_id)

    async def upsert(self, user_id: str, profile: UserProfileRecord) -> UserProfileRecord:
        self.profiles[user_id] = profile
        return profile

    async def get_for_companion(
        self, user_id: str, companion_id: int
    ) -> CompanionUserProfileRecord | None:
        return self.companion_profiles.get((user_id, companion_id))

    async def upsert_for_companion(
        self, user_id: str, companion_id: int, profile: CompanionUserProfileRecord
    ) -> CompanionUserProfileRecord:
        self.companion_profiles[(user_id, companion_id)] = profile
        return profile


def _clean(value: str | None, limit: int) -> str:
    return (value or "").strip()[:limit]


def normalize(profile: UserProfileRecord) -> UserProfileRecord:
    age = profile.age
    if age is not None and not 18 <= age <= 99:
        raise InvalidInput("年龄需在 18–99 之间", code="PROFILE_INVALID")
    return UserProfileRecord(
        nickname=_clean(profile.nickname, MAX_NICKNAME),
        identity=_clean(profile.identity, MAX_IDENTITY),
        age=age,
        gender=_clean(profile.gender, 8),
        city=_clean(profile.city, MAX_CITY),
        background=_clean(profile.background, MAX_BACKGROUND),
    )


def merge(
    base: UserProfileRecord | None,
    override: CompanionUserProfileRecord | None,
) -> UserProfileRecord:
    """伴侣级字段非空则覆盖通用字段；空则回落。"""
    merged = UserProfileRecord(
        nickname=base.nickname if base else "",
        identity=base.identity if base else "",
        age=base.age if base else None,
        gender=base.gender if base else "",
        city=base.city if base else "",
        background=base.background if base else "",
    )
    if override is None:
        return merged
    if override.nickname:
        merged.nickname = override.nickname
    if override.identity:
        merged.identity = override.identity
    if override.age is not None:
        merged.age = override.age
    if override.gender:
        merged.gender = override.gender
    if override.city:
        merged.city = override.city
    if override.background:
        merged.background = override.background
    return merged


def compile_for_prompt(profile: UserProfileRecord | None) -> str:
    """编译成“# 关于用户”片段；完全为空时返回空串，不污染提示词。"""
    if profile is None:
        return ""
    lines: list[str] = []
    if profile.nickname:
        lines.append(f"- 用户希望你称呼他/她：{profile.nickname}")
    if profile.identity:
        lines.append(f"- 用户身份：{profile.identity}")
    if profile.age is not None:
        lines.append(f"- 用户年龄：{profile.age} 岁")
    if profile.gender:
        lines.append(f"- 用户性别：{profile.gender}")
    if profile.city:
        lines.append(f"- 用户所在城市：{profile.city}")
    if profile.background:
        lines.append(f"- 用户补充背景：{profile.background}")
    if not lines:
        return ""
    return (
        "\n\n# 关于用户\n"
        + "\n".join(lines)
        + "\n（这些是用户自己的设定，自然使用，不要逐条复述。）"
    )


class UserProfileService:
    def __init__(self, repo: UserProfileRepository) -> None:
        self._repo = repo

    async def get(self, user_id: str) -> UserProfileRecord:
        return await self._repo.get(user_id) or UserProfileRecord()

    async def update(self, user_id: str, profile: UserProfileRecord) -> UserProfileRecord:
        return await self._repo.upsert(user_id, normalize(profile))

    async def get_for_companion(
        self, user_id: str, companion_id: int
    ) -> CompanionUserProfileRecord | None:
        return await self._repo.get_for_companion(user_id, companion_id)

    async def update_for_companion(
        self, user_id: str, companion_id: int, profile: CompanionUserProfileRecord
    ) -> CompanionUserProfileRecord:
        cleaned = CompanionUserProfileRecord(
            companion_id=companion_id,
            nickname=_clean(profile.nickname, MAX_NICKNAME) or None,
            identity=_clean(profile.identity, MAX_IDENTITY) or None,
            age=profile.age,
            gender=_clean(profile.gender, 8) or None,
            city=_clean(profile.city, MAX_CITY) or None,
            background=_clean(profile.background, MAX_BACKGROUND) or None,
        )
        if cleaned.age is not None and not 18 <= cleaned.age <= 99:
            raise InvalidInput("年龄需在 18–99 之间", code="PROFILE_INVALID")
        return await self._repo.upsert_for_companion(user_id, companion_id, cleaned)

    async def effective(self, user_id: str, companion_id: int) -> UserProfileRecord:
        base = await self._repo.get(user_id)
        override = await self._repo.get_for_companion(user_id, companion_id)
        return merge(base, override)

    async def prompt_for(self, user_id: str, companion_id: int) -> str:
        return compile_for_prompt(await self.effective(user_id, companion_id))
