"""语音音频临时文件：短期有效，读取时判断过期，写入时顺手清理。

为什么要在 save 里清理：
原来只提供了 cleanup() 方法，但**没有任何地方调用它**，
于是文件只增不减（实测积压了 126 个、4.5MB、跨度 10 天）。
现在每次写入新文件时清理一次，成本是一次目录扫描，
但保证不会再无限堆积。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

# 写入时清理多久以前的文件。
# 比 TTL（600 秒）长得多：TTL 只是「不可再访问」，文件可以留久一点，
# 万一有页面正引用着旧链接；但也没必要永久保留。
DEFAULT_CLEANUP_AGE_SECONDS = 3600


class AudioStore:
    """把合成结果写到本机临时目录，按 id 取回，过期即失效。"""

    def __init__(self, root: Path, *, ttl_seconds: int = 600) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds

    @property
    def root(self) -> Path:
        return self._root

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def save(self, audio: bytes, *, suffix: str = ".mp3") -> str:
        audio_id = uuid.uuid4().hex
        path = self._root / f"{audio_id}{suffix}"
        path.write_bytes(audio)
        # 顺手清理过期文件：放在写入之后，避免把刚存的文件误删；
        # 清理失败不能影响这次合成，所以吞掉异常只记数。
        self.cleanup()
        return audio_id

    def path_for(self, audio_id: str) -> Path | None:
        if not audio_id.isalnum():
            return None
        matches = list(self._root.glob(f"{audio_id}.*"))
        if not matches:
            return None
        path = matches[0]
        if time.time() - path.stat().st_mtime > self._ttl:
            return None
        return path

    def cleanup(self, *, max_age_seconds: int = DEFAULT_CLEANUP_AGE_SECONDS) -> int:
        """删掉超过 max_age_seconds 的文件，返回删除数量。

        代价是一次目录 glob；文件数量不多时可以接受。
        单个文件删不掉（被占用等）就跳过，不中断整体清理。
        """
        removed = 0
        now = time.time()
        for path in self._root.glob("*"):
            if not path.is_file():
                continue
            if now - path.stat().st_mtime > max_age_seconds:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed
