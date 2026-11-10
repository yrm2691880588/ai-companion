"""测试共享工具：一次性把所有仓储换成内存实现。

为什么需要这个：

`create_app()` 对**没传入**的仓储会创建 SQL 版本，而 SQL 版本会去连真实
PostgreSQL。本地开发时数据库通常开着，所以测试能过；但 CI 上（GitHub
Actions）没有数据库，同一个测试就会失败——本地环境把缺陷掩盖了。

这个工厂把所有仓储显式传成内存版，让测试不依赖任何外部服务。
新增仓储时请同步加到这里，否则该仓储仍会去连真实库。

用法：
    from tests.support import build_test_app
    app = build_test_app()
    app = build_test_app(settings=Settings(local_mode=False))
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.auth import InMemoryAuthRepository
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository
from app.domain.deletion import InMemoryDeletionRepository
from app.domain.memory import InMemoryMemoryRepository
from app.domain.quota import InMemoryQuotaRepository
from app.domain.roleplay import InMemoryRunRepository, InMemoryScenarioRepository
from app.domain.safety import InMemorySafetyRepository
from app.domain.system_settings import InMemorySystemSettingsRepository
from app.domain.templates import InMemoryTemplateRepository
from app.domain.usage import InMemoryUsageRepository
from app.infra.summary_repo import InMemorySummaryRepository
from app.main import create_app


def build_test_app(settings: Settings | None = None, **overrides: object) -> FastAPI:
    """构造一个不连任何外部服务的 app。

    overrides 里可以覆盖任意仓储（例如传入预置数据的 InMemoryTemplateRepository），
    其余没指定的都用内存版。
    """
    defaults: dict[str, object] = {
        "usage_repo": InMemoryUsageRepository(),
        "companion_repo": InMemoryCompanionRepository(),
        # 模板仓储要求传入数据；默认给空，需要预置模板时用 overrides 覆盖
        "template_repo": InMemoryTemplateRepository(()),
        "chat_repo": InMemoryChatRepository(),
        "memory_repo": InMemoryMemoryRepository(),
        "summary_repo": InMemorySummaryRepository(),
        "scenario_repo": InMemoryScenarioRepository(()),
        "run_repo": InMemoryRunRepository(),
        "safety_repo": InMemorySafetyRepository(),
        "quota_repo": InMemoryQuotaRepository(),
        "auth_repo": InMemoryAuthRepository(),
        "deletion_repo": InMemoryDeletionRepository(),
        "system_settings_repo": InMemorySystemSettingsRepository(),
    }
    defaults.update(overrides)
    resolved = settings or Settings(env="test", _env_file=None)  # type: ignore[call-arg]
    return create_app(resolved, **defaults)  # type: ignore[arg-type]


def build_test_client(settings: Settings | None = None, **overrides: object) -> TestClient:
    return TestClient(build_test_app(settings, **overrides))


def iter_repositories() -> Iterator[str]:
    """列出工厂覆盖的仓储名，供测试自检用。"""
    yield from (
        "usage_repo",
        "companion_repo",
        "template_repo",
        "chat_repo",
        "memory_repo",
        "summary_repo",
        "scenario_repo",
        "run_repo",
        "safety_repo",
        "quota_repo",
        "auth_repo",
        "deletion_repo",
        "system_settings_repo",
    )
