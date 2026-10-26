"""把历史账号数据统一到本地用户（开源本地模式迁移）。

用法：
    backend/.venv/Scripts/python.exe scripts/unify_local_user.py --target local-user
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.infra.db import build_engine  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="local-user")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = build_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            tables = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND column_name='user_id' "
                        "ORDER BY table_name"
                    )
                )
            ).scalars().all()

            total = 0
            skip_unique = {"user_profiles"}
            for table in tables:
                if table in skip_unique:
                    # 账号级身份只保留目标用户那条，其余删除，避免唯一约束冲突
                    removed = await conn.execute(
                        text(f'DELETE FROM "{table}" WHERE user_id <> :target'),
                        {"target": args.target},
                    )
                    if removed.rowcount:
                        print(f"{table}: 删除 {removed.rowcount} 行旧身份")
                        total += removed.rowcount
                    continue
                if table == "daily_usage":
                    merged = await conn.execute(
                        text(
                            "UPDATE daily_usage AS d SET turns = d.turns + s.turns "
                            "FROM daily_usage AS s "
                            "WHERE s.user_id <> :target AND d.user_id = :target AND d.day = s.day"
                        ),
                        {"target": args.target},
                    )
                    removed = await conn.execute(
                        text("DELETE FROM daily_usage WHERE user_id <> :target"),
                        {"target": args.target},
                    )
                    if merged.rowcount or removed.rowcount:
                        print(f"daily_usage: 合并 {merged.rowcount} 天，清理 {removed.rowcount} 行")
                        total += merged.rowcount + removed.rowcount
                    continue
                result = await conn.execute(
                    text(f'UPDATE "{table}" SET user_id = :target WHERE user_id <> :target'),
                    {"target": args.target},
                )
                if result.rowcount:
                    print(f"{table}: 迁移 {result.rowcount} 行")
                    total += result.rowcount

            if args.dry_run:
                await conn.rollback()
                print(f"[dry-run] 共影响 {total} 行，未提交。")
            else:
                await conn.commit()
                print(f"完成：所有数据归到 {args.target}，共 {total} 行。")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
