"""语音音频临时文件：短期有效，定时清理。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path


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

    def cleanup(self, *, max_age_seconds: int = 3600) -> int:
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
