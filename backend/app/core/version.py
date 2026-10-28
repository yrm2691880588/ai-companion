"""版本信息：唯一真源是 backend/pyproject.toml 的 version。

其它地方（FastAPI 标题、前端展示）都从这里派生，避免升级时漏改。
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "ai-companion-api"
FALLBACK_VERSION = "0.0.0"


@lru_cache(maxsize=1)
def app_version() -> str:
    """返回已安装版本；开发环境未安装时退回默认值，不抛异常。"""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return FALLBACK_VERSION


@lru_cache(maxsize=1)
def migration_head() -> str:
    """当前应达到的迁移版本，用于前端提示数据库是否落后。"""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    return heads[0] if heads else ""
