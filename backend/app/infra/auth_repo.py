"""登录：Postgres 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.auth import AccountRecord, CodeRecord, LoginSession
from app.models.auth import Account, AuthCode, AuthSession


class SqlAuthRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_account(self, phone: str) -> AccountRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(Account).where(Account.phone == phone))
            ).scalar_one_or_none()
        return _to_account(row) if row is not None else None

    async def find_account_by_id(self, account_id: int) -> AccountRecord | None:
        async with self._session_factory() as session:
            row = await session.get(Account, account_id)
        return _to_account(row) if row is not None else None

    async def create_account(self, phone: str) -> AccountRecord:
        async with self._session_factory() as session:
            row = Account(phone=phone)
            session.add(row)
            await session.commit()
            return _to_account(row)

    async def latest_code(self, phone: str) -> CodeRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(AuthCode)
                    .where(AuthCode.phone == phone, AuthCode.used.is_(False))
                    .order_by(AuthCode.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return _to_code(row) if row is not None else None

    async def save_code(self, phone: str, code_hash: str, expires_at: datetime) -> CodeRecord:
        async with self._session_factory() as session:
            row = AuthCode(phone=phone, code_hash=code_hash, expires_at=expires_at)
            session.add(row)
            await session.commit()
            return _to_code(row)

    async def mark_code_used(self, code_id: int) -> None:
        async with self._session_factory() as session:
            await session.execute(update(AuthCode).where(AuthCode.id == code_id).values(used=True))
            await session.commit()

    async def increment_attempts(self, code_id: int) -> int:
        async with self._session_factory() as session:
            row = await session.get(AuthCode, code_id)
            if row is None:
                return 0
            row.attempts += 1
            await session.commit()
            return row.attempts

    async def create_session(self, account_id: int, token_hash: str, expires_at: datetime) -> None:
        async with self._session_factory() as session:
            session.add(
                AuthSession(account_id=account_id, token_hash=token_hash, expires_at=expires_at)
            )
            await session.commit()

    async def find_session(self, token_hash: str) -> LoginSession | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(AuthSession).where(
                        AuthSession.token_hash == token_hash,
                        AuthSession.revoked_at.is_(None),
                        AuthSession.expires_at > datetime.now(UTC),
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return LoginSession(
            account_id=row.account_id, token_hash=row.token_hash, expires_at=row.expires_at
        )

    async def revoke_session(self, token_hash: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.token_hash == token_hash)
                .values(revoked_at=datetime.now(UTC))
            )
            await session.commit()

    async def touch_login(self, account_id: int) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(Account)
                .where(Account.id == account_id)
                .values(last_login_at=datetime.now(UTC))
            )
            await session.commit()


def _to_account(row: Account) -> AccountRecord:
    return AccountRecord(
        id=row.id, phone=row.phone, nickname=row.nickname, created_at=row.created_at
    )


def _to_code(row: AuthCode) -> CodeRecord:
    return CodeRecord(
        id=row.id,
        phone=row.phone,
        code_hash=row.code_hash,
        expires_at=row.expires_at,
        attempts=row.attempts,
        used=row.used,
        created_at=row.created_at,
    )
