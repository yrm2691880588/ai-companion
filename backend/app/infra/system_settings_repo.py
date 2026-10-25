"""系统设置与管理员审计：Postgres 实现。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.system_settings import SETTINGS_KEY
from app.models.admin import AdminAudit, SystemSetting


class SqlSystemSettingsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load(self) -> dict[str, object]:
        async with self._session_factory() as session:
            row = await session.get(SystemSetting, SETTINGS_KEY)
        return dict(row.value) if row is not None else {}

    async def save(self, value: dict[str, object], actor: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(SystemSetting, SETTINGS_KEY)
            if row is None:
                session.add(SystemSetting(key=SETTINGS_KEY, value=value, updated_by=actor))
            else:
                row.value = value
                row.updated_by = actor
            await session.commit()

    async def audit(
        self,
        actor: str,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
    ) -> None:
        async with self._session_factory() as session:
            session.add(AdminAudit(actor_user_id=actor, action=action, before=before, after=after))
            await session.commit()

    async def audit_tail(self, limit: int = 20) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AdminAudit).order_by(AdminAudit.id.desc()).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "id": row.id,
                "actor": row.actor_user_id,
                "action": row.action,
                "before": row.before,
                "after": row.after,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
