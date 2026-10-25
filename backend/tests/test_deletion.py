import pytest

from app.core.errors import NotFound
from app.domain.deletion import DeletionService, InMemoryDeletionRepository


async def test_enqueue_and_run_purges() -> None:
    repo = InMemoryDeletionRepository()
    service = DeletionService(repo)
    job = await service.enqueue("u1", 7)
    counts = await service.run_job(job.id)
    assert counts["companions"] == 1
    assert repo.purged == [("u1", 7)]
    record = await repo.get(job.id)
    assert record is not None and record.status == "done"
    assert "sessions:1" in (record.detail or "")


async def test_second_run_is_idempotent() -> None:
    repo = InMemoryDeletionRepository()
    service = DeletionService(repo)
    job = await service.enqueue("u1", 7)
    await service.run_job(job.id)
    again = await service.run_job(job.id)
    assert again == {}
    assert len(repo.purged) == 1


async def test_failure_marks_failed_and_attempts() -> None:
    repo = InMemoryDeletionRepository()
    repo.fail_next = True
    service = DeletionService(repo)
    job = await service.enqueue("u1", 7)
    with pytest.raises(RuntimeError):
        await service.run_job(job.id)
    record = await repo.get(job.id)
    assert record is not None
    assert record.status == "failed"
    assert record.attempts == 1


async def test_reconcile_runs_pending_jobs() -> None:
    repo = InMemoryDeletionRepository()
    service = DeletionService(repo)
    first = await service.enqueue("u1", 1)
    second = await service.enqueue("u2", 2)
    results = await service.reconcile()
    assert {item["job_id"] for item in results} == {first.id, second.id}
    assert all(item["ok"] for item in results)
    assert await repo.pending() == []


async def test_unknown_job_raises() -> None:
    service = DeletionService(InMemoryDeletionRepository())
    with pytest.raises(NotFound):
        await service.run_job(999)
