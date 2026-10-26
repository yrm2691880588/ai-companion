"""跨端唯一 ID：ULID（48 位毫秒时间 + 80 位随机，Crockford Base32）。"""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    timestamp = int(time.time() * 1000) & ((1 << 48) - 1)
    value = (timestamp << 80) | int.from_bytes(os.urandom(10), "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))
