"""自定义模型持久化：导入后可恢复。"""

from __future__ import annotations

from app.domain.custom_models import CustomModel, InMemoryCustomModelRepository


async def test_add_many_dedupes() -> None:
    repo = InMemoryCustomModelRepository()
    added = await repo.add_many(
        [
            CustomModel(provider_key="deepseek", model_name="a", display_name="A"),
            CustomModel(provider_key="deepseek", model_name="a", display_name="A"),
            CustomModel(provider_key="deepseek", model_name="b", display_name="B"),
        ]
    )
    assert added == 2
    assert len(await repo.all()) == 2


async def test_add_many_second_call_adds_nothing() -> None:
    repo = InMemoryCustomModelRepository()
    models = [CustomModel(provider_key="deepseek", model_name="a", display_name="A")]
    assert await repo.add_many(models) == 1
    assert await repo.add_many(models) == 0
