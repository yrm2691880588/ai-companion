"""登录：手机验证码 + 会话令牌（Cookie）。

- 验证码 6 位、5 分钟有效、60 秒内不可重复发送、最多试 5 次；
- 会话令牌随机 32 字节，数据库只存 SHA-256；
- 开发模式可以把验证码直接返回（sms_debug），生产接短信服务商。
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.core.errors import AppError, InvalidInput

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
COOKIE_NAME = "ac_session"
CODE_TTL_SECONDS = 300
RESEND_SECONDS = 60
MAX_ATTEMPTS = 5
SESSION_DAYS = 7


def normalize_phone(phone: str) -> str:
    value = re.sub(r"[\s-]", "", phone or "")
    if not PHONE_RE.match(value):
        raise InvalidInput("请输入 11 位手机号", code="INVALID_PHONE")
    return value


def mask_phone(phone: str) -> str:
    if len(phone) != 11:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


def hash_code(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}".encode()).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class AccountRecord:
    id: int
    phone: str
    nickname: str = ""
    created_at: datetime | None = None


@dataclass(slots=True)
class CodeRecord:
    id: int
    phone: str
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    used: bool = False
    created_at: datetime | None = None


@dataclass(slots=True)
class LoginSession:
    account_id: int
    token_hash: str
    expires_at: datetime


class AuthRepository(Protocol):
    async def find_account(self, phone: str) -> AccountRecord | None: ...

    async def find_account_by_id(self, account_id: int) -> AccountRecord | None: ...

    async def create_account(self, phone: str) -> AccountRecord: ...

    async def latest_code(self, phone: str) -> CodeRecord | None: ...

    async def save_code(self, phone: str, code_hash: str, expires_at: datetime) -> CodeRecord: ...

    async def mark_code_used(self, code_id: int) -> None: ...

    async def increment_attempts(self, code_id: int) -> int: ...

    async def create_session(
        self, account_id: int, token_hash: str, expires_at: datetime
    ) -> None: ...

    async def find_session(self, token_hash: str) -> LoginSession | None: ...

    async def revoke_session(self, token_hash: str) -> None: ...

    async def touch_login(self, account_id: int) -> None: ...


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self.accounts: dict[str, AccountRecord] = {}
        self.codes: list[CodeRecord] = []
        self.sessions: dict[str, LoginSession] = {}
        self._next_account_id = 1
        self._next_code_id = 1

    async def find_account(self, phone: str) -> AccountRecord | None:
        return self.accounts.get(phone)

    async def find_account_by_id(self, account_id: int) -> AccountRecord | None:
        return next((item for item in self.accounts.values() if item.id == account_id), None)

    async def create_account(self, phone: str) -> AccountRecord:
        record = AccountRecord(id=self._next_account_id, phone=phone, created_at=datetime.now(UTC))
        self.accounts[phone] = record
        self._next_account_id += 1
        return record

    async def latest_code(self, phone: str) -> CodeRecord | None:
        matches = [item for item in self.codes if item.phone == phone and not item.used]
        return matches[-1] if matches else None

    async def save_code(self, phone: str, code_hash: str, expires_at: datetime) -> CodeRecord:
        record = CodeRecord(
            id=self._next_code_id,
            phone=phone,
            code_hash=code_hash,
            expires_at=expires_at,
            created_at=datetime.now(UTC),
        )
        self.codes.append(record)
        self._next_code_id += 1
        return record

    async def mark_code_used(self, code_id: int) -> None:
        for item in self.codes:
            if item.id == code_id:
                item.used = True

    async def increment_attempts(self, code_id: int) -> int:
        for item in self.codes:
            if item.id == code_id:
                item.attempts += 1
                return item.attempts
        return 0

    async def create_session(self, account_id: int, token_hash: str, expires_at: datetime) -> None:
        self.sessions[token_hash] = LoginSession(
            account_id=account_id, token_hash=token_hash, expires_at=expires_at
        )

    async def find_session(self, token_hash: str) -> LoginSession | None:
        item = self.sessions.get(token_hash)
        if item is None or item.expires_at <= datetime.now(UTC):
            return None
        return item

    async def revoke_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    async def touch_login(self, account_id: int) -> None:
        for item in self.accounts.values():
            if item.id == account_id:
                item.created_at = item.created_at or datetime.now(UTC)


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        *,
        sms_debug: bool = True,
        code_ttl_seconds: int = CODE_TTL_SECONDS,
        session_days: int = SESSION_DAYS,
    ) -> None:
        self._repo = repo
        self.sms_debug = sms_debug
        self._code_ttl = code_ttl_seconds
        self._session_days = session_days

    async def request_code(self, phone: str) -> tuple[str, datetime]:
        normalized = normalize_phone(phone)
        now = datetime.now(UTC)
        latest = await self._repo.latest_code(normalized)
        if latest is not None and latest.created_at is not None:
            elapsed = (now - latest.created_at).total_seconds()
            if elapsed < RESEND_SECONDS:
                raise AppError(
                    code="SMS_TOO_FREQUENT",
                    message=f"验证码发送太频繁，请 {RESEND_SECONDS - int(elapsed)} 秒后再试",
                    status_code=429,
                )
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = now + timedelta(seconds=self._code_ttl)
        await self._repo.save_code(normalized, hash_code(normalized, code), expires_at)
        return code, expires_at

    async def login(self, phone: str, code: str) -> tuple[str, AccountRecord, datetime]:
        normalized = normalize_phone(phone)
        if not re.fullmatch(r"\d{6}", code or ""):
            raise InvalidInput("验证码为 6 位数字", code="INVALID_CODE")
        record = await self._repo.latest_code(normalized)
        if record is None or record.expires_at <= datetime.now(UTC):
            raise AppError(code="CODE_EXPIRED", message="验证码已过期，请重新获取", status_code=401)
        if record.attempts >= MAX_ATTEMPTS:
            raise AppError(code="CODE_LOCKED", message="尝试次数过多，请重新获取", status_code=401)
        if hash_code(normalized, code) != record.code_hash:
            await self._repo.increment_attempts(record.id)
            raise AppError(code="CODE_INVALID", message="验证码不正确", status_code=401)
        await self._repo.mark_code_used(record.id)
        account = await self._repo.find_account(normalized) or await self._repo.create_account(
            normalized
        )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=self._session_days)
        await self._repo.create_session(account.id, hash_token(token), expires_at)
        await self._repo.touch_login(account.id)
        return token, account, expires_at

    async def resolve_account_id(self, token: str) -> int | None:
        if not token:
            return None
        session = await self._repo.find_session(hash_token(token))
        return session.account_id if session is not None else None

    async def logout(self, token: str) -> None:
        if token:
            await self._repo.revoke_session(hash_token(token))

    async def me(self, account_id: int) -> AccountRecord | None:
        return await self._repo.find_account_by_id(account_id)
