"""当前请求的设备标识：请求进来时设置，写入数据时取用。

没有设备标识时退回 "local"，保证本地单机模式行为不变。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

DEVICE_HEADER = "X-Device-Id"
LOCAL_DEVICE = "local"

_current: ContextVar[str] = ContextVar("current_device_id", default=LOCAL_DEVICE)


def current_device_id() -> str:
    return _current.get()


@contextmanager
def device_scope(device_id: str | None) -> Iterator[None]:
    """在请求处理期间固定设备标识。"""
    cleaned = (device_id or "").strip()[:64] or LOCAL_DEVICE
    token = _current.set(cleaned)
    try:
        yield
    finally:
        _current.reset(token)
