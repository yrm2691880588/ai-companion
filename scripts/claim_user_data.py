"""把未登录（dev-user）时期创建的数据迁移到某个手机号账号。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/claim_user_data.py --phone 13800001234

要求：这个手机号至少登录过一次（账号已存在）。脚本只改 user_id，不动消息内容。
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
    parser.add_argument("--phone", required=True, help="目标账号手机号（需已登录过一次）")
    parser.add_argument("--source", default="dev-user", help="被迁移的旧用户 id")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不提交")
    args = parser.parse_args()

    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT id FROM accounts WHERE phone = :phone"),
                    {"phone": args.phone},
                )
            ).first()
            if row is None:
                print(f"账号 {args.phone} 不存在，请先用它登录一次再迁移。")
                return 1
            target = str(row[0])
            if target == args.source:
                print("源用户与目标账号相同，无需迁移。")
                return 0

            tables = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND column_name = 'user_id' "
                        "ORDER BY table_name"
                    )
                )
            ).scalars().all()

            total = 0
            for table in tables:
                if table == "daily_usage":
                    # 目标账号当天可能已有额度行：先合并 turns，再删旧行
                    merged = await conn.execute(
                        text(
                            "UPDATE daily_usage AS d SET turns = d.turns + s.turns "
                            "FROM daily_usage AS s "
                            "WHERE s.user_id = :source AND d.user_id = :target AND d.day = s.day"
                        ),
                        {"target": target, "source": args.source},
                    )
                    removed = await conn.execute(
                        text("DELETE FROM daily_usage WHERE user_id = :source"),
                        {"source": args.source},
                    )
                    if merged.rowcount or removed.rowcount:
                        print(
                            f"daily_usage: 合并 {merged.rowcount} 天，清理 {removed.rowcount} 行"
                        )
                        total += merged.rowcount + removed.rowcount
                    continue
                result = await conn.execute(
                    text(f'UPDATE "{table}" SET user_id = :target WHERE user_id = :source'),
                    {"target": target, "source": args.source},
                )
                if result.rowcount:
                    print(f"{table}: 迁移 {result.rowcount} 行")
                    total += result.rowcount
            if args.dry_run:
                await conn.rollback()
                print(f"[dry-run] 共影响 {total} 行，未提交。")
            else:
                await conn.commit()
                print(f"完成：{args.source} → 账号 {args.phone}（id={target}），共 {total} 行。")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
