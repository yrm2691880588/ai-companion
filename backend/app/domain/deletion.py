"""彻底删除：软删后异步硬清，失败可补偿重试。

口径：
- 用户删除伴侣后立刻从列表消失（软删）；
- 后台任务删除伴侣行，依赖外键级联清理人设版本、会话、消息、摘要、记忆、演练；
- 安全事件没有外键，需要先按会话删掉；
- 删除任务留痕（不含内容），失败可重试，便于 24h 对账。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.core.errors import NotFound


@dataclass(slots=True)
class DeletionJobRecord:
    id: int
    user_id: str
    companion_id: int
    status: str
    attempts: int
    detail: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None


class DeletionRepository(Protocol):
    async def enqueue(self, user_id: str, companion_id: int) -> DeletionJobRecord: ...

    async def get(self, job_id: int) -> DeletionJobRecord | None: ...

    async def pending(self, limit: int = 20) -> list[DeletionJobRecord]: ...

    async def mark_done(self, job_id: int, detail: str) -> None: ...

    async def mark_failed(self, job_id: int, detail: str) -> None: ...

    async def purge(self, user_id: str, companion_id: int) -> dict[str, int]: ...


class InMemoryDeletionRepository:
    def __init__(self) -> None:
        self.jobs: dict[int, DeletionJobRecord] = {}
        self.purged: list[tuple[str, int]] = []
        self.fail_next = False
        self._next_id = 1

    async def enqueue(self, user_id: str, companion_id: int) -> DeletionJobRecord:
        record = DeletionJobRecord(
            id=self._next_id,
            user_id=user_id,
            companion_id=companion_id,
            status="pending",
            attempts=0,
            created_at=datetime.now(UTC),
        )
        self.jobs[record.id] = record
        self._next_id += 1
        return record

    async def get(self, job_id: int) -> DeletionJobRecord | None:
        return self.jobs.get(job_id)

    async def pending(self, limit: int = 20) -> list[DeletionJobRecord]:
        items = [item for item in self.jobs.values() if item.status == "pending"]
        return items[:limit]

    async def mark_done(self, job_id: int, detail: str) -> None:
        record = self.jobs[job_id]
        record.status = "done"
        record.detail = detail
        record.processed_at = datetime.now(UTC)

    async def mark_failed(self, job_id: int, detail: str) -> None:
        record = self.jobs[job_id]
        record.status = "failed"
        record.detail = detail
        record.attempts += 1
        record.processed_at = datetime.now(UTC)

    async def purge(self, user_id: str, companion_id: int) -> dict[str, int]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("purge failed")
        self.purged.append((user_id, companion_id))
        return {"companions": 1, "sessions": 1, "messages": 2, "memories": 1}


class DeletionService:
    def __init__(self, repo: DeletionRepository) -> None:
        self._repo = repo

    async def enqueue(self, user_id: str, companion_id: int) -> DeletionJobRecord:
        return await self._repo.enqueue(user_id, companion_id)

    async def run_job(self, job_id: int) -> dict[str, int]:
        job = await self._repo.get(job_id)
        if job is None:
            raise NotFound("删除任务不存在")
        if job.status == "done":
            return {}
        try:
            counts = await self._repo.purge(job.user_id, job.companion_id)
        except Exception as exc:  # noqa: BLE001 - 失败要留痕并可重试
            await self._repo.mark_failed(job_id, str(exc)[:500])
            raise
        detail = ",".join(f"{key}:{value}" for key, value in counts.items())
        await self._repo.mark_done(job_id, detail)
        return counts

    async def reconcile(self, limit: int = 20) -> list[dict[str, object]]:
        """补偿：把仍处于 pending 的任务再跑一遍。"""
        results: list[dict[str, object]] = []
        for job in await self._repo.pending(limit):
            try:
                counts = await self.run_job(job.id)
                results.append({"job_id": job.id, "ok": True, "counts": counts})
            except Exception as exc:  # noqa: BLE001
                results.append({"job_id": job.id, "ok": False, "error": str(exc)})
        return results
