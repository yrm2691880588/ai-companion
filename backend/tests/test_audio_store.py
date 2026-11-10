"""AudioStore：临时音频的写入、取回、过期失效与自动清理。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.infra.audio_store import AudioStore


def test_save_and_read_back(tmp_path: Path) -> None:
    store = AudioStore(tmp_path)
    audio_id = store.save(b"fake-mp3-bytes")
    path = store.path_for(audio_id)
    assert path is not None
    assert path.read_bytes() == b"fake-mp3-bytes"


def test_expired_file_is_unreadable(tmp_path: Path) -> None:
    """超过 TTL 的文件不再可访问，但文件本身还在（等清理）。"""
    store = AudioStore(tmp_path, ttl_seconds=1)
    audio_id = store.save(b"x")
    path = tmp_path / f"{audio_id}.mp3"
    old = time.time() - 10
    os.utime(path, (old, old))
    assert store.path_for(audio_id) is None
    assert path.exists()


def test_path_for_rejects_non_alnum(tmp_path: Path) -> None:
    """路径穿越防护：id 必须是纯字母数字。"""
    store = AudioStore(tmp_path)
    assert store.path_for("../etc/passwd") is None
    assert store.path_for("a/b") is None


def test_save_triggers_cleanup_of_old_files(tmp_path: Path) -> None:
    """关键回归：save 会顺手清掉过期文件。

    之前 cleanup() 写好了却没人调用，导致文件只增不减
    （实测积压 126 个、4.5MB、跨度 10 天）。
    """
    store = AudioStore(tmp_path)
    # 造一个 2 小时前的旧文件
    stale = tmp_path / "stale.mp3"
    stale.write_bytes(b"old")
    old = time.time() - 7200
    os.utime(stale, (old, old))

    store.save(b"new")

    assert not stale.exists(), "过期文件应被清理"
    # 刚存的文件不能被误删
    assert len(list(tmp_path.glob("*.mp3"))) == 1


def test_recent_file_survives_cleanup(tmp_path: Path) -> None:
    store = AudioStore(tmp_path)
    fresh = tmp_path / "fresh.mp3"
    fresh.write_bytes(b"recent")
    removed = store.cleanup()
    assert removed == 0
    assert fresh.exists()


def test_cleanup_reports_count(tmp_path: Path) -> None:
    store = AudioStore(tmp_path)
    for index in range(3):
        path = tmp_path / f"old{index}.mp3"
        path.write_bytes(b"x")
        old = time.time() - 7200
        os.utime(path, (old, old))
    assert store.cleanup() == 3


def test_startup_cleanup_removes_leftovers(tmp_path: Path) -> None:
    """启动时清理上次残留。

    场景：用户合成一次语音就关闭后端，那个文件不会被 save 清理到
    （save 只在合成时触发）。下次启动必须把它清掉，
    否则会一直堆着，直到下一次合成。
    """
    from app.core.config import Settings
    from app.main import create_app

    stale = tmp_path / "leftover.mp3"
    stale.write_bytes(b"old")
    old = time.time() - 7200
    os.utime(stale, (old, old))

    create_app(
        Settings(env="test", audio_dir=str(tmp_path), _env_file=None)  # type: ignore[call-arg]
    )

    assert not stale.exists(), "启动时应清理上次残留"


def test_startup_cleanup_keeps_recent_files(tmp_path: Path) -> None:
    """启动清理不能误删刚生成、可能还在播的文件。"""
    from app.core.config import Settings
    from app.main import create_app

    fresh = tmp_path / "playing.mp3"
    fresh.write_bytes(b"recent")

    create_app(
        Settings(env="test", audio_dir=str(tmp_path), _env_file=None)  # type: ignore[call-arg]
    )

    assert fresh.exists(), "刚生成的文件不应被启动清理删掉"
