"""API 依赖：登录态解析与领域服务获取。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.domain.auth import COOKIE_NAME, AuthService
from app.domain.chat import ChatService
from app.domain.companions import CompanionService
from app.domain.deletion import DeletionService
from app.domain.roleplay import RoleplayService
from app.domain.templates import TemplateRepository
from app.domain.usage import UsageRepository
from app.infra.summary_repo import SummaryRepository


async def get_current_user_id(request: Request) -> str:
    """本地模式固定本机用户；否则优先 Cookie 会话，开发模式允许 X-User-Id 兜底。"""
    settings = request.app.state.settings
    if getattr(settings, "local_mode", False):
        return getattr(settings, "local_user_id", "local-user")
    service = getattr(request.app.state, "auth_service", None)
    token = request.cookies.get(COOKIE_NAME, "")
    if token and isinstance(service, AuthService):
        account_id = await service.resolve_account_id(token)
        if account_id is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "登录已过期，请重新登录"},
            )
        return str(account_id)
    if settings.debug_auth:
        return request.headers.get("X-User-Id") or settings.debug_user_id
    raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "请先登录"})


def get_companion_service(request: Request) -> CompanionService:
    service = getattr(request.app.state, "companion_service", None)
    if not isinstance(service, CompanionService):
        raise HTTPException(status_code=503, detail="伴侣服务尚未初始化")
    return service


def get_usage_repo(request: Request) -> UsageRepository:
    repo = getattr(request.app.state, "usage_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="用量统计暂不可用")
    return repo


def get_template_repo(request: Request) -> TemplateRepository:
    repo = getattr(request.app.state, "template_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="模板服务暂不可用")
    return repo


def get_chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if not isinstance(service, ChatService):
        raise HTTPException(status_code=503, detail="对话服务尚未初始化")
    return service


def get_summary_repo(request: Request) -> SummaryRepository:
    repo = getattr(request.app.state, "summary_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="摘要服务暂不可用")
    return repo


def get_roleplay_service(request: Request) -> RoleplayService:
    service = getattr(request.app.state, "roleplay_service", None)
    if not isinstance(service, RoleplayService):
        raise HTTPException(status_code=503, detail="演练服务尚未初始化")
    return service


def get_deletion_service(request: Request) -> DeletionService:
    service = getattr(request.app.state, "deletion_service", None)
    if not isinstance(service, DeletionService):
        raise HTTPException(status_code=503, detail="删除服务尚未初始化")
    return service


async def require_admin(request: Request, user_id: str = Depends(get_current_user_id)) -> str:
    settings = request.app.state.settings
    if getattr(settings, "local_mode", False):
        return user_id
    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthService) and user_id.isdigit():
        if await service.is_admin(int(user_id)):
            return user_id
    raise HTTPException(
        status_code=403,
        detail={"code": "FORBIDDEN", "message": "需要管理员权限"},
    )

