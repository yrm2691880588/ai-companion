"""本地模式：没有账号、没有管理员，所有人都是同一个本机用户。"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", local_mode=True, local_user_id="local-user", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            llm_client=FakeLLM(),
        )
    )


def test_me_reports_local_mode() -> None:
    payload = client().get("/v1/me").json()
    assert payload["local_mode"] is True
    assert payload["role"] == "local"
    assert payload["user_id"] == "local-user"


def test_header_cannot_switch_user_in_local_mode() -> None:
    test_client = client()
    first = test_client.post("/v1/companions", json={"persona": _persona()}).json()
    other = test_client.get("/v1/companions", headers={"X-User-Id": "someone-else"}).json()
    assert any(item["id"] == first["id"] for item in other)


def test_admin_endpoints_open_in_local_mode() -> None:
    response = client().get("/v1/admin/settings")
    assert response.status_code == 200


def _persona() -> dict[str, object]:
    return {
        "name": "本地测试",
        "identity": "测试角色",
        "gender": "不设定",
        "age": 25,
        "personality": ["安静", "可靠"],
        "speaking_style": "句子短，语气平稳。",
        "background": "仅用于自动化测试的临时角色，不会被真实使用。",
        "tags": ["测试"],
        "relationship": "测试关系",
    }
