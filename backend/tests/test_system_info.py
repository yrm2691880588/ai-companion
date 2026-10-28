"""系统信息与更新检查：版本来源、未配置时不联网、上游异常不编造。"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.version import app_version, migration_head
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


def client(**overrides: object) -> TestClient:
    settings = Settings(env="test", _env_file=None, **overrides)  # type: ignore[call-arg]
    return TestClient(
        create_app(
            settings,
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            llm_client=FakeLLM(),
        )
    )


def test_version_comes_from_package_metadata() -> None:
    assert app_version() == "0.1.0"


def test_migration_head_is_known() -> None:
    assert migration_head().startswith("00")


def test_system_info_reports_version_and_head() -> None:
    body = client().get("/v1/system/info").json()
    assert body["version"] == "0.1.0"
    assert body["migration_head"]
    assert body["local_mode"] is True


def test_update_check_without_feed_does_not_guess() -> None:
    body = client().get("/v1/system/update-check").json()
    assert body["checked"] is False
    assert body["latest"] is None
    assert body["update_available"] is False
    assert "未配置" in body["reason"]


def test_update_check_reports_unreachable_feed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import httpx

    class Boom:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.api.v1.system.httpx.AsyncClient", lambda **kwargs: Boom())
    body = (
        client(update_feed="https://example.invalid/releases").get("/v1/system/update-check").json()
    )
    assert body["checked"] is False
    assert body["latest"] is None
    assert "检查失败" in body["reason"]
