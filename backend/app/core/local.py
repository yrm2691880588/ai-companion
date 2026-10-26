"""本地模式：没有账号、没有管理员，只有一个本机用户。"""

from __future__ import annotations

from fastapi import Request


def is_local_mode(request: Request) -> bool:
    settings = request.app.state.settings
    return bool(getattr(settings, "local_mode", False))


def local_user_id(request: Request) -> str:
    settings = request.app.state.settings
    return getattr(settings, "local_user_id", "local-user")
