"""会话与消息：Postgres 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.device import current_device_id
from app.core.ids import new_ulid
from app.domain.chat import MessageRecord, SessionRecord
from app.domain.sync import record
from app.models.chat import ChatMessage, ChatSession


class SqlChatRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(
        self, user_id: str, companion_id: int, title: str = ""
    ) -> SessionRecord:
        async with self._session_factory() as session:
            row = ChatSession(
                user_id=user_id,
                companion_id=companion_id,
                title=title,
                ulid=new_ulid(),
                origin_device_id=current_device_id(),
            )
            session.add(row)
            await session.flush()
            record(
                session,
                entity_type="session",
                entity_ulid=row.ulid,
                operation="create",
                payload={"companion_id": companion_id, "title": title},
            )
            await session.commit()
            return SessionRecord(
                id=row.id,
                ulid=row.ulid,
                companion_id=companion_id,
                user_id=user_id,
                title=title,
                state="active",
                created_at=row.created_at or datetime.now(UTC),
                last_message_at=None,
            )

    async def list_sessions(self, user_id: str, companion_id: int) -> list[SessionRecord]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ChatSession)
                        .where(
                            ChatSession.user_id == user_id,
                            ChatSession.companion_id == companion_id,
                            ChatSession.deleted_at.is_(None),
                        )
                        .order_by(
                            func.coalesce(
                                ChatSession.last_message_at, ChatSession.created_at
                            ).desc()
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [_to_session(row) for row in rows]

    async def get_session(self, user_id: str, session_id: int) -> SessionRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(
                        ChatSession.id == session_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        return _to_session(row) if row is not None else None

    async def list_messages(
        self, user_id: str, session_id: int, *, before_seq: int | None = None, limit: int = 20
    ) -> list[MessageRecord]:
        async with self._session_factory() as session:
            stmt = (
                select(ChatMessage)
                .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatSession.user_id == user_id,
                    ChatSession.deleted_at.is_(None),
                    ChatMessage.deleted_at.is_(None),
                )
            )
            if before_seq is not None:
                stmt = stmt.where(ChatMessage.seq < before_seq)
            rows = (
                (await session.execute(stmt.order_by(ChatMessage.seq.desc()).limit(limit)))
                .scalars()
                .all()
            )
        return [_to_message(row) for row in reversed(rows)]

    async def latest_for_companion(self, user_id: str, companion_id: int) -> MessageRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatSession.companion_id == companion_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                        ChatMessage.deleted_at.is_(None),
                    )
                    .order_by(ChatMessage.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return _to_message(row) if row is not None else None

    async def append_message(
        self,
        user_id: str,
        session_id: int,
        role: str,
        content: str,
        client_request_id: str | None = None,
    ) -> MessageRecord:
        async with self._session_factory() as session:
            owned = (
                await session.execute(
                    select(ChatSession.id).where(
                        ChatSession.id == session_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if owned is None:
                raise ValueError("会话不存在")
            max_seq = (
                await session.execute(
                    select(func.coalesce(func.max(ChatMessage.seq), 0)).where(
                        ChatMessage.session_id == session_id
                    )
                )
            ).scalar_one()
            row = ChatMessage(
                session_id=session_id,
                seq=int(max_seq) + 1,
                role=role,
                content=content,
                client_request_id=client_request_id,
                ulid=new_ulid(),
                origin_device_id=current_device_id(),
            )
            session.add(row)
            chat_session = await session.get(ChatSession, session_id)
            if chat_session is not None:
                chat_session.last_message_at = datetime.now(UTC)
            await session.flush()
            record(
                session,
                entity_type="message",
                entity_ulid=row.ulid,
                operation="append",
                payload={"session_id": session_id, "role": role, "seq": row.seq},
            )
            await session.commit()
            return _to_message(row)

    async def find_by_request(
        self, user_id: str, session_id: int, client_request_id: str
    ) -> MessageRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.client_request_id == client_request_id,
                        ChatSession.user_id == user_id,
                        ChatMessage.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        return _to_message(row) if row is not None else None

    async def get_message(self, user_id: str, message_id: int) -> MessageRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatMessage.id == message_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                        ChatMessage.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        return _to_message(row) if row is not None else None

    async def update_message(
        self, user_id: str, message_id: int, content: str
    ) -> MessageRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatMessage.id == message_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                        ChatMessage.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.content = content
            await session.commit()
            return _to_message(row)

    async def touch_session(
        self, user_id: str, session_id: int, *, title: str | None = None
    ) -> None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(
                        ChatSession.id == session_id, ChatSession.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.last_message_at = datetime.now(UTC)
            if title:
                row.title = title
            await session.commit()

    async def delete_session(self, user_id: str, session_id: int) -> bool:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(
                        ChatSession.id == session_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.deleted_at = datetime.now(UTC)
            row.state = "deleted"
            await session.commit()
            return True

    async def rename_session(
        self, user_id: str, session_id: int, title: str
    ) -> SessionRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(
                        ChatSession.id == session_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.title = title
            await session.commit()
            return _to_session(row)

    async def delete_message(self, user_id: str, message_id: int) -> bool:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatMessage.id == message_id,
                        ChatSession.user_id == user_id,
                        ChatSession.deleted_at.is_(None),
                        ChatMessage.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            # 同步预留：保留墓碑，不物理删除
            row.deleted_at = datetime.now(UTC)
            await session.commit()
            return True


def _to_session(row: ChatSession) -> SessionRecord:
    return SessionRecord(
        id=row.id,
        ulid=row.ulid,
        companion_id=row.companion_id,
        user_id=row.user_id,
        title=row.title,
        state=row.state,
        created_at=row.created_at,
        last_message_at=row.last_message_at,
    )


def _to_message(row: ChatMessage) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        ulid=row.ulid,
        session_id=row.session_id,
        seq=row.seq,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
        client_request_id=row.client_request_id,
    )
