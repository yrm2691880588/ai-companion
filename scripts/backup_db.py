"""整库备份与恢复：把全部业务数据导出为单个 JSON 文件。

设计要点：
- 不依赖 pg_dump：自部署用户可能没装 PostgreSQL 客户端，纯 Python 直连即可；
- 覆盖全部业务表，跳过运行期临时表（认证会话、验证码、审计流水、同步 outbox）；
- 备份文件带 format/version 与创建时间，恢复端据此判断兼容性；
- 恢复采用「先清空再写入」，只用于同版本之间迁移，不做跨版本数据修复。

用法：
    python scripts/backup_db.py --out tmp/backup.json
    python scripts/backup_db.py --restore tmp/backup.json --yes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import MetaData, Table, delete, insert, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.infra.db import build_engine  # noqa: E402

BACKUP_FORMAT = "ai-companion-backup"
BACKUP_VERSION = 1

# 运行期临时表：不进备份。恢复后重建即可，带着反而会造成过期会话/重复流水。
SKIP_TABLES = {
    "alembic_version",  # 迁移版本由 alembic 自己管理
    "auth_codes",  # 一次性验证码
    "auth_sessions",  # 登录会话，换机器应当失效
    "admin_audit",  # 操作审计，属于本机历史
    "sync_outbox",  # 同步队列，未消费的事件不应迁移
    "llm_calls",  # 调用流水，体量大且非用户数据
    "voice_usage",  # 语音用量流水
    "analytics_events",  # 埋点流水
    "deletion_jobs",  # 待执行的删除任务
    "daily_usage",  # 每日额度计数
}


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"__type__": "bytes", "value": value.hex()}
    return value


def from_jsonable(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__type__"):
        kind = value["__type__"]
        raw = value["value"]
        if kind == "datetime":
            return datetime.fromisoformat(raw)
        if kind == "decimal":
            return Decimal(raw)
        if kind == "bytes":
            return bytes.fromhex(raw)
    return value


async def dump(conn: AsyncConnection, tables: list[Table]) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        rows = (await conn.execute(select(table))).mappings().all()
        data[table.name] = [
            {key: to_jsonable(value) for key, value in row.items()} for row in rows
        ]
    return data


async def backup(out_path: Path) -> int:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            metadata = MetaData()
            await conn.run_sync(metadata.reflect)
            tables = [
                table
                for name, table in metadata.tables.items()
                if name not in SKIP_TABLES
            ]
            tables.sort(key=lambda item: item.name)
            data = await dump(conn, tables)

        payload = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "tables": {table.name: len(rows) for table, rows in zip(tables, data.values())},
            "data": data,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total = sum(len(rows) for rows in data.values())
        print(f"备份完成：{out_path}（{len(data)} 张表，{total} 行）")
        return 0
    finally:
        await engine.dispose()


def sort_by_dependency(metadata: MetaData, names: list[str]) -> list[str]:
    """按外键依赖排序：被引用的表先写，引用别人的表后写。

    同时存在环时（极少见）保留原顺序，避免死循环。
    """
    wanted = set(names)
    deps: dict[str, set[str]] = {name: set() for name in names}
    for name in names:
        table = metadata.tables[name]
        for foreign_key in table.foreign_keys:
            target = foreign_key.column.table.name
            if target in wanted and target != name:
                deps[name].add(target)

    ordered: list[str] = []
    resolved: set[str] = set()
    pending = list(names)
    while pending:
        progressed = False
        for name in list(pending):
            if deps[name] <= resolved:
                ordered.append(name)
                resolved.add(name)
                pending.remove(name)
                progressed = True
        if not progressed:
            # 存在循环依赖：剩下的按原顺序写入，避免死等
            ordered.extend(pending)
            break
    return ordered


async def restore(in_path: Path, *, assume_yes: bool) -> int:
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    if payload.get("format") != BACKUP_FORMAT:
        raise SystemExit("不是本项目的备份文件")
    if payload.get("version") != BACKUP_VERSION:
        raise SystemExit(
            f"备份版本 {payload.get('version')} 与当前 {BACKUP_VERSION} 不匹配，请先升级备份"
        )
    if not assume_yes:
        raise SystemExit("恢复会清空现有数据，确认后加 --yes 再执行")

    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            metadata = MetaData()
            await conn.run_sync(metadata.reflect)
            data: dict[str, list[dict[str, Any]]] = payload["data"]

            # 先按依赖倒序清空，再按拓扑顺序写入，避免外键冲突
            names = [name for name in data if name in metadata.tables]
            ordered = sort_by_dependency(metadata, names)
            for name in reversed(ordered):
                await conn.execute(delete(metadata.tables[name]))
            for name in ordered:
                table = metadata.tables[name]
                rows = [
                    {key: from_jsonable(value) for key, value in row.items()}
                    for row in data[name]
                ]
                if rows:
                    await conn.execute(insert(table), rows)
                print(f"已恢复 {name}：{len(rows)} 行")
        print("恢复完成")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="整库备份与恢复")
    parser.add_argument("--out", type=Path, default=Path("tmp/backup.json"))
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if args.restore:
        return asyncio.run(restore(args.restore, assume_yes=args.yes))
    return asyncio.run(backup(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
