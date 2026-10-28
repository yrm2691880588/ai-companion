"""系统信息：版本、迁移状态、可选的更新检查。

用途：
- 前端「我的」页展示当前版本；
- 自部署用户想知道有没有新版；
- 排障时确认数据库迁移是否落后。

更新检查只读公开的 Release 地址，不发送任何用户数据；
未配置 `AI_COMPANION_UPDATE_FEED` 时返回「未配置」，不编造版本号。
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user_id
from app.core.version import app_version, migration_head

router = APIRouter(prefix="/v1/system", tags=["system"])

UserDep = Annotated[str, Depends(get_current_user_id)]


@router.get("/info")
async def system_info(request: Request, _user: UserDep) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "version": app_version(),
        "migration_head": migration_head(),
        "local_mode": bool(getattr(settings, "local_mode", False)),
        "update_feed_configured": bool(getattr(settings, "update_feed", "")),
    }


@router.get("/update-check")
async def update_check(request: Request, _user: UserDep) -> dict[str, Any]:
    """检查是否有新版本；未配置更新源时不联网、不猜测。"""
    feed = str(getattr(request.app.state.settings, "update_feed", "") or "").strip()
    current = app_version()
    if not feed:
        return {
            "checked": False,
            "reason": "未配置 AI_COMPANION_UPDATE_FEED，本地模式不联网检查",
            "current": current,
            "latest": None,
            "update_available": False,
        }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(feed, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "checked": False,
            "reason": f"检查失败：{exc}",
            "current": current,
            "latest": None,
            "update_available": False,
        }

    latest = str(payload.get("tag_name") or payload.get("version") or "").strip()
    return {
        "checked": True,
        "reason": "",
        "current": current,
        "latest": latest or None,
        "update_available": bool(latest and latest.lstrip("v") != current),
        "url": payload.get("html_url"),
    }
