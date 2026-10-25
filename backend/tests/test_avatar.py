import base64
from decimal import Decimal

import pytest

from app.core.errors import InvalidInput, NotFound
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.usage import CallContext
from app.infra.llm.types import Usage

PERSONA = Persona.model_validate(
    {
        "name": "曼曼",
        "identity": "夜店驻唱歌手",
        "gender": "女",
        "age": 27,
        "personality": ["大胆", "黏人"],
        "speaking_style": "说话带点沙哑的懒腔，句子短。",
        "background": "在城南一家小酒馆驻唱，晚上上班白天睡觉，作息和大多数人反着来。",
        "tags": ["夜场歌手"],
        "relationship": "住在你楼上的邻居",
    }
)

# 1x1 PNG
PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lK3Q6wAAAABJRU5ErkJggg=="
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


async def build():
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM())
    record = await service.create("u1", PERSONA)
    return service, record


async def test_set_and_clear_avatar() -> None:
    service, record = await build()
    updated = await service.set_avatar("u1", record.id, PNG)
    assert updated.avatar == PNG
    cleared = await service.set_avatar("u1", record.id, None)
    assert cleared.avatar is None


async def test_reject_non_image_data_url() -> None:
    service, record = await build()
    with pytest.raises(InvalidInput):
        await service.set_avatar("u1", record.id, "data:text/plain;base64,aGk=")


async def test_reject_oversized_avatar() -> None:
    service, record = await build()
    payload = "data:image/png;base64," + base64.b64encode(b"x" * (300 * 1024 + 1)).decode()
    with pytest.raises(InvalidInput) as excinfo:
        await service.set_avatar("u1", record.id, payload)
    assert excinfo.value.code == "AVATAR_TOO_LARGE"


async def test_avatar_is_per_user() -> None:
    service, record = await build()
    with pytest.raises(NotFound):
        await service.set_avatar("u2", record.id, PNG)
