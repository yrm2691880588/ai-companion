"""用户身份接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id
from app.core.errors import AppError
from app.domain.user_profile import (
    CompanionUserProfileRecord,
    UserProfileRecord,
    UserProfileService,
)

router = APIRouter(prefix="/v1/me", tags=["profile"])


class ProfileIn(BaseModel):
    nickname: str = Field(default="", max_length=20)
    identity: str = Field(default="", max_length=60)
    age: int | None = Field(default=None, ge=18, le=99)
    gender: str = Field(default="", max_length=8)
    city: str = Field(default="", max_length=40)
    background: str = Field(default="", max_length=400)


class ProfileOut(ProfileIn):
    pass


class CompanionProfileIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=20)
    identity: str | None = Field(default=None, max_length=60)
    age: int | None = Field(default=None, ge=18, le=99)
    gender: str | None = Field(default=None, max_length=8)
    city: str | None = Field(default=None, max_length=40)
    background: str | None = Field(default=None, max_length=400)


class CompanionProfileOut(CompanionProfileIn):
    companion_id: int
    effective: ProfileOut


def get_service(request: Request) -> UserProfileService:
    service = getattr(request.app.state, "user_profile_service", None)
    if not isinstance(service, UserProfileService):
        raise AppError(code="PROFILE_UNAVAILABLE", message="身份服务未初始化", status_code=503)
    return service


ServiceDep = Annotated[UserProfileService, Depends(get_service)]
UserDep = Annotated[str, Depends(get_current_user_id)]


def _out(record: UserProfileRecord) -> ProfileOut:
    return ProfileOut(
        nickname=record.nickname,
        identity=record.identity,
        age=record.age,
        gender=record.gender,
        city=record.city,
        background=record.background,
    )


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user_id: UserDep, service: ServiceDep) -> ProfileOut:
    return _out(await service.get(user_id))


@router.put("/profile", response_model=ProfileOut)
async def update_profile(payload: ProfileIn, user_id: UserDep, service: ServiceDep) -> ProfileOut:
    record = UserProfileRecord(
        nickname=payload.nickname,
        identity=payload.identity,
        age=payload.age,
        gender=payload.gender,
        city=payload.city,
        background=payload.background,
    )
    return _out(await service.update(user_id, record))


@router.get("/companions/{companion_id}/profile", response_model=CompanionProfileOut)
async def get_companion_profile(
    companion_id: int, user_id: UserDep, service: ServiceDep
) -> CompanionProfileOut:
    override = await service.get_for_companion(user_id, companion_id)
    effective = await service.effective(user_id, companion_id)
    return CompanionProfileOut(
        companion_id=companion_id,
        nickname=override.nickname if override else None,
        identity=override.identity if override else None,
        age=override.age if override else None,
        gender=override.gender if override else None,
        city=override.city if override else None,
        background=override.background if override else None,
        effective=_out(effective),
    )


@router.put("/companions/{companion_id}/profile", response_model=CompanionProfileOut)
async def update_companion_profile(
    companion_id: int,
    payload: CompanionProfileIn,
    user_id: UserDep,
    service: ServiceDep,
) -> CompanionProfileOut:
    record = CompanionUserProfileRecord(
        companion_id=companion_id,
        nickname=payload.nickname,
        identity=payload.identity,
        age=payload.age,
        gender=payload.gender,
        city=payload.city,
        background=payload.background,
    )
    await service.update_for_companion(user_id, companion_id, record)
    return await get_companion_profile(companion_id, user_id, service)
