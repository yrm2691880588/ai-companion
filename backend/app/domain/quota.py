"""每日轮次限额：对话与演练每个用户回合消耗 1 次。

口径：
- 按北京时间自然日计；
- 对话与演练共用同一个 60 轮/日额度；
- 首 token 前失败会返还次数（避免网络问题白扣）；
- 用数据库原子更新保证多实例下不超卖（Redis 只是可选加速）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from app.core.errors import AppError

SHANGHAI = timezone(timedelta(hours=8))


def today_in_shanghai() -> date:
    return datetime.now(SHANGHAI).date()


@dataclass(frozen=True, slots=True)
class QuotaState:
    day: date
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


class QuotaRepository(Protocol):
    async def consume(self, user_id: str, day: date, limit: int) -> int:
        """原子地占用一次；超出上限时抛 ValueError。"""

    async def get(self, user_id: str, day: date) -> int: ...

    async def refund(self, user_id: str, day: date) -> None: ...


class InMemoryQuotaRepository:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}

    async def consume(self, user_id: str, day: date, limit: int) -> int:
        key = (user_id, day)
        current = self._counts.get(key, 0)
        if current >= limit:
            raise ValueError("quota exceeded")
        self._counts[key] = current + 1
        return current + 1

    async def get(self, user_id: str, day: date) -> int:
        return self._counts.get((user_id, day), 0)

    async def refund(self, user_id: str, day: date) -> None:
        key = (user_id, day)
        self._counts[key] = max(self._counts.get(key, 0) - 1, 0)


class QuotaService:
    def __init__(self, repo: QuotaRepository, *, daily_limit: int = 60) -> None:
        self._repo = repo
        self._limit = max(daily_limit, 1)

    @property
    def limit(self) -> int:
        return self._limit

    async def status(self, user_id: str) -> QuotaState:
        day = today_in_shanghai()
        used = await self._repo.get(user_id, day)
        return QuotaState(day=day, used=used, limit=self._limit)

    async def ensure_available(self, user_id: str) -> QuotaState:
        state = await self.status(user_id)
        if state.used >= state.limit:
            raise AppError(
                code="QUOTA_EXCEEDED",
                message=f"今天的 {state.limit} 轮已经用完，明天再来吧",
                status_code=429,
                details={"limit": state.limit, "used": state.used, "day": state.day.isoformat()},
            )
        return state

    async def consume(self, user_id: str) -> QuotaState:
        day = today_in_shanghai()
        try:
            used = await self._repo.consume(user_id, day, self._limit)
        except ValueError as exc:
            raise AppError(
                code="QUOTA_EXCEEDED",
                message=f"今天的 {self._limit} 轮已经用完，明天再来吧",
                status_code=429,
                details={"limit": self._limit, "used": self._limit, "day": day.isoformat()},
            ) from exc
        return QuotaState(day=day, used=used, limit=self._limit)

    async def refund(self, user_id: str) -> None:
        await self._repo.refund(user_id, today_in_shanghai())
