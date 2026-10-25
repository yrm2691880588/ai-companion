"""官方模板：表结构 + Postgres 实现（启动时按代码里的模板做幂等同步）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.persona import Persona
from app.domain.templates import Template
from app.models.companions import CompanionTemplate


class SqlTemplateRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, category: str | None = None) -> list[Template]:
        async with self._session_factory() as session:
            stmt = select(CompanionTemplate).where(CompanionTemplate.enabled.is_(True))
            if category:
                stmt = stmt.where(CompanionTemplate.category == category)
            rows = (await session.execute(stmt.order_by(CompanionTemplate.key))).scalars().all()
        return [_to_template(row) for row in rows]

    async def get(self, key: str) -> Template | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(CompanionTemplate).where(CompanionTemplate.key == key))
            ).scalar_one_or_none()
        return _to_template(row) if row is not None else None

    async def sync(self, templates: tuple[Template, ...]) -> int:
        """把代码里的模板同步进数据库：新增插入，已有则更新（幂等）。"""
        async with self._session_factory() as session:
            existing = {
                row.key: row
                for row in (await session.execute(select(CompanionTemplate))).scalars().all()
            }
            for item in templates:
                payload = {
                    "category": item.category,
                    "name": item.name,
                    "tagline": item.tagline,
                    "persona": item.persona.model_dump(mode="json"),
                    "enabled": True,
                }
                row = existing.get(item.key)
                if row is None:
                    session.add(CompanionTemplate(key=item.key, **payload))
                else:
                    for field_name, value in payload.items():
                        setattr(row, field_name, value)
            await session.commit()
        return len(templates)


def _to_template(row: CompanionTemplate) -> Template:
    return Template(
        key=row.key,
        category=row.category,
        name=row.name,
        tagline=row.tagline,
        persona=Persona.model_validate(row.persona),
    )
