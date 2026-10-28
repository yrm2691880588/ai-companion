"""日志落地：把运行期错误写到文件，便于用户导出后排查。

设计约束（对应 AGENTS.md 的隐私与可观测要求）：
- **不记录请求体与对话内容**，只记时间、路径、错误码、堆栈、版本；
- 文件按大小轮转，避免无限增长；
- 日志目录可由 `AI_COMPANION_LOG_DIR` 指定；留空时用仓库下的 `logs/`；
- 写入失败不能影响主流程（吃异常但打一条 warning 到标准输出）。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "app.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
_HANDLER_MARK = "ai-companion-file"


def resolve_log_dir(configured: str) -> Path:
    """日志目录：配置优先，否则用仓库根下的 logs/。"""
    if configured.strip():
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "logs"


def setup_file_logging(log_dir: Path, *, level: int = logging.INFO) -> Path | None:
    """给根 logger 挂一个轮转文件处理器；重复调用不会重复挂。

    返回日志文件路径；目录不可写时返回 None（不阻断启动）。
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if (
            getattr(handler, "name", "") == _HANDLER_MARK
            or getattr(handler, "_dsh_mark", "") == _HANDLER_MARK
        ):
            base = getattr(handler, "baseFilename", "")
            return Path(base) if base else None

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / LOG_FILENAME
        handler = RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        handler._dsh_mark = _HANDLER_MARK  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.setLevel(level)
        root.addHandler(handler)
        # 根 logger 级别不能低于处理器，否则 INFO 被提前丢弃
        if root.level == logging.NOTSET or root.level > level:
            root.setLevel(level)
        return path
    except OSError as exc:
        logging.getLogger(__name__).warning("日志目录不可写，仅输出到控制台：%s", exc)
        return None
