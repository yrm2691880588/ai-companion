"""应用配置：全部通过环境变量注入，前缀 AI_COMPANION_。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # 优先读仓库根目录的 .env（单一来源），工作目录里的 .env 可覆盖
    model_config = SettingsConfigDict(
        env_prefix="AI_COMPANION_",
        env_file=(str(REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ai-companion-api"
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # 数据与缓存
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/companion"
    redis_url: str = "redis://localhost:6379/0"

    # 密钥：32 字节的 base64（或 64 位 hex），用于信封加密供应商 API Key
    master_key: str = ""

    # 开发期鉴权占位：生产必须关闭
    debug_auth: bool = True
    debug_user_id: str = "dev-user"

    # 本地模型：是否允许访问 localhost / 私有网段（单机自用模式打开，公网多用户模式关闭）
    allow_private_model_endpoints: bool = False

    # 模型层默认值
    # 命中率默认取 0.75：2026-10-25 实测短前缀只有 52%，长会话会逐步升高，取中位偏保守
    default_hit_ratio: float = 0.75
    turn_cost_cap_cny: float = 0.02
    expected_output_tokens: int = 500
    max_context_ratio: float = 0.8
    chat_context_budget_tokens: int = 8000
    daily_turn_limit: int = 60

    # 登录：开发模式可回显验证码；生产接短信服务商后关闭
    sms_debug: bool = True
    session_days: int = 7
    # 管理员手机号（逗号分隔），登录时自动授予 admin
    admin_phones: str = ""
    # 本地单用户模式（开源默认）：没有账号、没有管理员
    local_mode: bool = True
    local_user_id: str = "local-user"
    # 前端构建产物目录；留空则用仓库下的 frontend/dist
    frontend_dist: str = ""

    @property
    def admin_phone_set(self) -> set[str]:
        return {item.strip() for item in self.admin_phones.split(",") if item.strip()}

    # 供应商密钥（.env 里配置；不打印、不返回）
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    kimi_api_key: str = ""
    glm_api_key: str = ""
    siliconflow_api_key: str = ""
    openai_api_key: str = ""

    def provider_keys(self) -> dict[str, str]:
        """返回「供应商 key → API Key」的映射，供模型注册表注入。"""
        return {
            "deepseek": self.deepseek_api_key,
            "qwen": self.qwen_api_key,
            "kimi": self.kimi_api_key,
            "glm": self.glm_api_key,
            "siliconflow": self.siliconflow_api_key,
            "openai": self.openai_api_key,
        }

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()

