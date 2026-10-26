"""用户身份：覆盖规则、字段回落、提示词注入、越权。"""

from __future__ import annotations

import pytest

from app.core.errors import InvalidInput
from app.domain.user_profile import (
    CompanionUserProfileRecord,
    InMemoryUserProfileRepository,
    UserProfileRecord,
    UserProfileService,
    compile_for_prompt,
    merge,
)


def build() -> UserProfileService:
    return UserProfileService(InMemoryUserProfileRepository())


async def test_general_profile_saved_and_returned() -> None:
    service = build()
    saved = await service.update(
        "u1",
        UserProfileRecord(
            nickname="小周",
            identity="后端工程师",
            age=27,
            gender="男",
            city="杭州",
            background="最近在准备考研",
        ),
    )
    assert saved.nickname == "小周"
    assert (await service.get("u1")).identity == "后端工程师"


async def test_companion_override_wins() -> None:
    service = build()
    await service.update("u1", UserProfileRecord(nickname="小周", identity="后端工程师", age=27))
    await service.update_for_companion(
        "u1",
        7,
        CompanionUserProfileRecord(companion_id=7, identity="她的学弟", age=None),
    )
    effective = await service.effective("u1", 7)
    assert effective.identity == "她的学弟"
    assert effective.nickname == "小周"  # 未覆盖的字段回落
    assert effective.age == 27


async def test_companion_override_can_clear_with_empty() -> None:
    service = build()
    await service.update("u1", UserProfileRecord(identity="后端工程师"))
    await service.update_for_companion(
        "u1", 7, CompanionUserProfileRecord(companion_id=7, identity="   ")
    )
    effective = await service.effective("u1", 7)
    assert effective.identity == "后端工程师"


async def test_prompt_contains_profile_fields() -> None:
    note = compile_for_prompt(
        UserProfileRecord(nickname="小周", identity="后端工程师", city="杭州")
    )
    assert "# 关于用户" in note
    assert "小周" in note
    assert "后端工程师" in note
    assert "杭州" in note


async def test_empty_profile_produces_no_note() -> None:
    assert compile_for_prompt(None) == ""
    assert compile_for_prompt(UserProfileRecord()) == ""


async def test_age_out_of_range_rejected() -> None:
    service = build()
    with pytest.raises(InvalidInput):
        await service.update("u1", UserProfileRecord(age=17))


def test_merge_prefers_override() -> None:
    base = UserProfileRecord(nickname="A", identity="B", age=30, city="C")
    override = CompanionUserProfileRecord(companion_id=1, nickname="D", age=22)
    merged = merge(base, override)
    assert merged.nickname == "D"
    assert merged.identity == "B"
    assert merged.age == 22
    assert merged.city == "C"
