"""自定义模型：持久化用户从供应商导入的模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.custom_models import CustomModelRow


@dataclass(slots=True)
class CustomModel:
    provider_key: str
    model_name: str
    display_name: str
    context_window: int = 32768
    max_output: int = 8192


class CustomModelRepository(Protocol):
    async def all(self) -> list[CustomModel]: ...

    async def add_many(self, models: list[CustomModel]) -> int: ...


class InMemoryCustomModelRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], CustomModel] = {}

    async def all(self) -> list[CustomModel]:
        return list(self._items.values())

    async def add_many(self, models: list[CustomModel]) -> int:
        added = 0
        for model in models:
            key = (model.provider_key, model.model_name)
            if key not in self._items:
                self._items[key] = model
                added += 1
        return added


class SqlCustomModelRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def all(self) -> list[CustomModel]:
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(CustomModelRow).order_by(CustomModelRow.id)))
                .scalars()
                .all()
            )
        return [
            CustomModel(
                provider_key=row.provider_key,
                model_name=row.model_name,
                display_name=row.display_name,
                context_window=row.context_window,
                max_output=row.max_output,
            )
            for row in rows
        ]

    async def add_many(self, models: list[CustomModel]) -> int:
        async with self._session_factory() as session:
            existing = set(
                (
                    await session.execute(
                        select(CustomModelRow.provider_key, CustomModelRow.model_name)
                    )
                ).all()
            )
            added = 0
            for model in models:
                key = (model.provider_key, model.model_name)
                if key in existing:
                    continue
                session.add(
                    CustomModelRow(
                        provider_key=model.provider_key,
                        model_name=model.model_name,
                        display_name=model.display_name,
                        context_window=model.context_window,
                        max_output=model.max_output,
                    )
                )
                added += 1
            await session.commit()
            return added
