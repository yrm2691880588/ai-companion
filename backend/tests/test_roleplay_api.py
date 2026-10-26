import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.quota import InMemoryQuotaRepository
from app.domain.roleplay import SCENARIOS, InMemoryRunRepository, InMemoryScenarioRepository
from app.domain.safety import InMemorySafetyRepository
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage
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

REVIEW = json.dumps(
    {
        "summary": "表达清楚，但缺少结果数据。",
        "scores": {"clarity": 4, "empathy": 3, "structure": 3, "confidence": 4},
        "highlights": ["开场简洁"],
        "improvements": ["补充量化结果"],
        "sample_lines": ["我负责的部分把转化率从 3% 提到 4.2%。"],
    },
    ensure_ascii=False,
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult(REVIEW, "fake:review", Usage(), Decimal("0"))


class FakeStreamer:
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="说说你的项目。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=5))


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(local_mode=False, env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            chat_repo=InMemoryChatRepository(),
            chat_streamer=FakeStreamer(),
            llm_client=FakeLLM(),
            scenario_repo=InMemoryScenarioRepository(SCENARIOS),
            run_repo=InMemoryRunRepository(),
            safety_repo=InMemorySafetyRepository(),
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def prepare(test_client: TestClient) -> tuple[int, int]:
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    run = test_client.post(
        f"/v1/companions/{companion['id']}/roleplay",
        json={"scenario_key": "interview_screen"},
    ).json()
    return companion["id"], run["id"]


def test_list_scenarios() -> None:
    payload = client().get("/v1/roleplay/scenarios").json()
    assert len(payload) == 5
    assert {item["key"] for item in payload} >= {"interview_screen", "stranger_talk"}


def test_start_roleplay_returns_opening() -> None:
    test_client = client()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    response = test_client.post(
        f"/v1/companions/{companion['id']}/roleplay",
        json={"scenario_key": "interview_screen"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "active"
    assert payload["opening"]
    assert payload["scenario"]["role"] == "面试官"


def test_roleplay_turn_and_finish_flow() -> None:
    test_client = client()
    companion_id, run_id = prepare(test_client)
    turn = test_client.post(f"/v1/roleplay/{run_id}/turns", json={"content": "你好，我叫小林。"})
    assert turn.status_code == 200
    assert "event: delta" in turn.text
    assert "说说你的项目" in turn.text
    run = test_client.get(f"/v1/roleplay/{run_id}").json()
    assert run["turns_played"] == 1

    review = test_client.post(f"/v1/roleplay/{run_id}/finish").json()
    assert review["status"] == "finished"
    assert review["review"]["scores"]["clarity"] == 4
    assert review["review"]["improvements"]


def test_roleplay_is_isolated_between_users() -> None:
    test_client = client()
    _, run_id = prepare(test_client)
    other = test_client.get(f"/v1/roleplay/{run_id}", headers={"X-User-Id": "u2"})
    assert other.status_code == 404
