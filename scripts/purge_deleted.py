"""删除任务对账脚本：把 pending 的硬清任务再跑一遍。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/purge_deleted.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.deletion import DeletionService  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.deletion_repo import SqlDeletionRepository  # noqa: E402


async def main() -> int:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    repo = SqlDeletionRepository(build_session_factory(engine))
    service = DeletionService(repo)

    results = await service.reconcile(limit=50)
    if not results:
        print("没有待处理的删除任务")
    for item in results:
        if item["ok"]:
            print(f"任务 {item['job_id']} 已完成：{item['counts']}")
        else:
            print(f"任务 {item['job_id']} 失败：{item['error']}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
