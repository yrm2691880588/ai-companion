"""登录接口：验证码、登录、退出、当前账号。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id
from app.domain.auth import COOKIE_NAME, AuthService, mask_phone

router = APIRouter(prefix="/v1/auth", tags=["auth"])
me_router = APIRouter(prefix="/v1", tags=["me"])


class SmsCodeIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11)


class SmsCodeOut(BaseModel):
    ok: bool = True
    expires_in: int
    debug_code: str | None = None


class LoginIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=6, max_length=6)


class LoginOut(BaseModel):
    account_id: int
    phone_masked: str
    expires_at: datetime


class MeOut(BaseModel):
    user_id: str
    account_id: int | None = None
    phone_masked: str | None = None
    role: str = "user"
    local_mode: bool = False
    created_at: datetime | None = None


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if not isinstance(service, AuthService):
        raise RuntimeError("登录服务尚未初始化")
    return service


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/sms-code", response_model=SmsCodeOut)
async def request_code(payload: SmsCodeIn, service: AuthDep) -> SmsCodeOut:
    code, _expires_at = await service.request_code(payload.phone)
    return SmsCodeOut(
        expires_in=300,
        # 仅在开发模式返回验证码，生产接短信服务商后必须关闭
        debug_code=code if service.sms_debug else None,
    )


@router.post("/login", response_model=LoginOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    service: AuthDep,
) -> LoginOut:
    token, account, expires_at = await service.login(payload.phone, payload.code)
    settings = request.app.state.settings
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.is_prod,
        path="/",
    )
    return LoginOut(
        account_id=account.id,
        phone_masked=mask_phone(account.phone),
        expires_at=expires_at,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, service: AuthDep) -> dict[str, bool]:
    token = request.cookies.get(COOKIE_NAME, "")
    await service.logout(token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@me_router.get("/me", response_model=MeOut)
async def me(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> MeOut:
    if getattr(request.app.state.settings, "local_mode", False):
        return MeOut(user_id=user_id, role="local", local_mode=True)
    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthService) and user_id.isdigit():
        account = await service.me(int(user_id))
        if account is not None:
            return MeOut(
                user_id=user_id,
                account_id=account.id,
                phone_masked=mask_phone(account.phone),
                role=account.role,
                created_at=account.created_at,
            )
    return MeOut(user_id=user_id)

