import base64
import os

import pytest

from app.security.crypto import (
    SecretBox,
    SecretCryptoError,
    SecretDecryptError,
    load_master_key,
    mask_secret,
)


def new_master() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def test_roundtrip() -> None:
    box = SecretBox(new_master())
    token = box.encrypt("sk-1234567890abcdef")
    assert token.startswith("enc:v1:")
    assert "sk-1234567890abcdef" not in token
    assert box.decrypt(token) == "sk-1234567890abcdef"


def test_ciphertext_is_randomized() -> None:
    box = SecretBox(new_master())
    first = box.encrypt("same-secret")
    second = box.encrypt("same-secret")
    assert first != second
    assert box.decrypt(first) == box.decrypt(second) == "same-secret"


def test_wrong_master_key_cannot_decrypt() -> None:
    token = SecretBox(new_master()).encrypt("secret")
    other = SecretBox(new_master())
    with pytest.raises(SecretDecryptError):
        other.decrypt(token)


def test_tampered_payload_is_rejected() -> None:
    box = SecretBox(new_master())
    token = box.encrypt("secret")
    prefix, payload = token.rsplit(":", 1)
    flipped = ("A" if payload[0] != "A" else "B") + payload[1:]
    with pytest.raises((SecretDecryptError, SecretCryptoError)):
        box.decrypt(f"{prefix}:{flipped}")


def test_master_key_accepts_hex_and_base64() -> None:
    raw = os.urandom(32)
    assert load_master_key(raw.hex()) == raw
    assert load_master_key(base64.b64encode(raw).decode()) == raw


def test_master_key_rejects_short_input() -> None:
    with pytest.raises(SecretCryptoError):
        load_master_key("abc")
    with pytest.raises(SecretCryptoError):
        load_master_key("")


def test_mask_secret() -> None:
    assert mask_secret("") == ""
    assert mask_secret("short") == "****"
    assert mask_secret("sk-1234567890abcd") == "sk-****abcd"
