"""同步 outbox：清理策略与统计。"""

from __future__ import annotations

from app.domain.sync import InMemoryOutboxRepository, OutboxEvent


def event(index: int) -> OutboxEvent:
    return OutboxEvent(
        entity_type="message",
        entity_ulid=f"01M5YE75Q1PMQN4XY3C9432P{index:02d}",
        operation="append",
    )


async def test_prune_keeps_recent() -> None:
    repo = InMemoryOutboxRepository()
    for index in range(150):
        await repo.append(event(index))
    assert (await repo.stats())["pending"] == 150

    removed = await repo.prune(keep=100)
    assert removed == 50
    assert (await repo.stats())["pending"] == 100


async def test_prune_noop_when_under_limit() -> None:
    repo = InMemoryOutboxRepository()
    for index in range(10):
        await repo.append(event(index))
    assert await repo.prune(keep=100) == 0
    assert (await repo.stats())["pending"] == 10


async def test_prune_enforces_minimum_keep() -> None:
    """keep 传很小的值也会被抬到 100，避免误删过多。"""
    repo = InMemoryOutboxRepository()
    for index in range(150):
        await repo.append(event(index))
    removed = await repo.prune(keep=1)
    assert removed == 50
    assert (await repo.stats())["pending"] == 100


async def test_stats_on_empty() -> None:
    repo = InMemoryOutboxRepository()
    assert (await repo.stats())["pending"] == 0
