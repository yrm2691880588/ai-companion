"""供应商密钥的信封加密：主密钥只解包数据密钥，数据密钥加密明文。

格式：enc:v1:<base64(包装后的数据密钥)>:<base64(nonce+密文)>
- 主密钥来自 AI_COMPANION_MASTER_KEY（32 字节 base64 或 64 位 hex），绝不入库；
- 每条密文使用独立的数据密钥与非随机数，避免同一主密钥下大量密文共享密钥；
- 解密失败（篡改/换主密钥）抛 SecretDecryptError，不返回半截明文。
"""

from __future__ import annotations

import base64
import binascii
import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX: Final = "enc:v1:"
KEY_BYTES: Final = 32
NONCE_BYTES: Final = 12


class SecretCryptoError(Exception):
    """密钥配置或密文格式错误。"""


class SecretDecryptError(SecretCryptoError):
    """密文无法解密（被篡改或主密钥已更换）。"""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as exc:
        raise SecretCryptoError("密文不是合法的 base64") from exc


def load_master_key(raw: str) -> bytes:
    """解析主密钥：支持 base64 与 hex 两种写法，必须是 32 字节。"""
    if not raw:
        raise SecretCryptoError("未配置 AI_COMPANION_MASTER_KEY")
    text = raw.strip()
    lengths: list[int] = []
    for decoder in (_b64decode, bytes.fromhex):
        try:
            key = decoder(text)
        except (SecretCryptoError, ValueError):
            continue
        if len(key) == KEY_BYTES:
            return key
        lengths.append(len(key))
    if lengths:
        raise SecretCryptoError(f"主密钥长度必须是 {KEY_BYTES} 字节，实际 {lengths[0]}")
    raise SecretCryptoError("主密钥既不是 base64 也不是 hex")


class SecretBox:
    def __init__(self, master_key: str | bytes) -> None:
        self._master = master_key if isinstance(master_key, bytes) else load_master_key(master_key)
        if len(self._master) != KEY_BYTES:
            raise SecretCryptoError(f"主密钥长度必须是 {KEY_BYTES} 字节")

    def encrypt(self, plaintext: str) -> str:
        dek = os.urandom(KEY_BYTES)
        dek_nonce = os.urandom(NONCE_BYTES)
        wrapped = AESGCM(self._master).encrypt(dek_nonce, dek, PREFIX.encode("ascii"))
        payload_nonce = os.urandom(NONCE_BYTES)
        payload = AESGCM(dek).encrypt(
            payload_nonce, plaintext.encode("utf-8"), PREFIX.encode("ascii")
        )
        return f"{PREFIX}{_b64encode(dek_nonce + wrapped)}:{_b64encode(payload_nonce + payload)}"

    def decrypt(self, token: str) -> str:
        if not token.startswith(PREFIX):
            raise SecretCryptoError("密文前缀不正确")
        body = token[len(PREFIX) :]
        parts = body.split(":")
        if len(parts) != 2:
            raise SecretCryptoError("密文结构不正确")
        wrapped_blob = _b64decode(parts[0])
        payload_blob = _b64decode(parts[1])
        if len(wrapped_blob) <= NONCE_BYTES or len(payload_blob) <= NONCE_BYTES:
            raise SecretCryptoError("密文长度不足")
        dek_nonce, wrapped = wrapped_blob[:NONCE_BYTES], wrapped_blob[NONCE_BYTES:]
        try:
            dek = AESGCM(self._master).decrypt(dek_nonce, wrapped, PREFIX.encode("ascii"))
        except InvalidTag as exc:
            raise SecretDecryptError("主密钥不匹配或密文被篡改") from exc
        payload_nonce, payload = payload_blob[:NONCE_BYTES], payload_blob[NONCE_BYTES:]
        try:
            plaintext = AESGCM(dek).decrypt(payload_nonce, payload, PREFIX.encode("ascii"))
        except InvalidTag as exc:
            raise SecretDecryptError("密文被篡改") from exc
        return plaintext.decode("utf-8")


def mask_secret(secret: str) -> str:
    """给前端看的掩码，例如 sk-****abcd。"""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"
