"""错误日志：文件落地、重复挂载、目录不可写、前端上报接口。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging_setup import LOG_FILENAME, resolve_log_dir, setup_file_logging
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


def client(log_dir: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", _env_file=None, log_dir=str(log_dir)),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            llm_client=FakeLLM(),
        )
    )


def _drop_file_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_dsh_mark", "") == "ai-companion-file":
            root.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def clean_handlers() -> Iterator[None]:
    """每个用例前后移除文件处理器，避免上一用例的挂载影响下一用例。"""
    _drop_file_handlers()
    yield
    _drop_file_handlers()


def test_resolve_log_dir_uses_config(tmp_path: Path) -> None:
    assert resolve_log_dir(str(tmp_path)) == tmp_path


def test_resolve_log_dir_defaults_to_repo_logs() -> None:
    assert resolve_log_dir("").name == "logs"


def test_setup_creates_file_and_is_idempotent(tmp_path: Path) -> None:
    first = setup_file_logging(tmp_path)
    second = setup_file_logging(tmp_path)
    assert first is not None
    assert second == first
    # 只应挂一个文件处理器
    marks = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_dsh_mark", "") == "ai-companion-file"
    ]
    assert len(marks) == 1


def test_setup_returns_none_when_unwritable(tmp_path: Path) -> None:
    """目录不可写时不能抛异常，返回 None 让应用照常启动。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    assert setup_file_logging(blocker) is None


def test_client_error_endpoint_writes_log(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    response = test_client.post(
        "/v1/system/client-error",
        json={
            "message": "渲染失败",
            "stack": "Error: 渲染失败\n    at App.tsx:1:1",
            "component": "ErrorBoundary",
            "url": "/me",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "logged"

    log_file = tmp_path / LOG_FILENAME
    content = log_file.read_text(encoding="utf-8")
    assert "渲染失败" in content
    assert "ErrorBoundary" in content


def test_client_error_rejects_overlong_message(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    response = test_client.post("/v1/system/client-error", json={"message": "x" * 600})
    assert response.status_code == 422
