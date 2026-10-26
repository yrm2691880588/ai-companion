import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.deletion import InMemoryDeletionRepository
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Message, TaskName, Usage
from app.main import create_app

PERSONA = {
    "name": "林夏",
    "identity": "心理学研究生",
    "gender": "女",
    "age": 24,
    "personality": ["温柔", "偶尔毒舌"],
    "speaking_style": "句子短，先共情再给建议。",
    "background": "在读心理学研究生，晚上在便利店兼职，见过很多深夜的人。",
    "tags": ["温柔", "学姐"],
    "relationship": "住在隔壁的学姐",
}


class FakeLLM:
    async def complete(
        self, task: TaskName, messages: list[Message], *, context: CallContext
    ) -> LLMResult:
        return LLMResult(json.dumps({"value": "ok"}), "fake:model", Usage(), Decimal("0"))


def client(deletion: InMemoryDeletionRepository) -> TestClient:
    return TestClient(
        create_app(
            Settings(local_mode=False, env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            llm_client=FakeLLM(),
            deletion_repo=deletion,
        )
    )


def test_delete_schedules_hard_purge() -> None:
    repo = InMemoryDeletionRepository()
    test_client = client(repo)
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()

    response = test_client.delete(
        f"/v1/companions/{companion['id']}?confirm_name={companion['name']}"
    )
    assert response.status_code == 204
    # BackgroundTasks 在 TestClient 里会同步执行完
    assert repo.purged == [("dev-user", companion["id"])]
    assert test_client.get("/v1/companions").json() == []
