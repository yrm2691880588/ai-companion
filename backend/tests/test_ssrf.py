import pytest

from app.core.errors import InvalidInput
from app.security.ssrf import validate_endpoint


def test_public_https_is_allowed_and_normalized() -> None:
    assert validate_endpoint("https://api.deepseek.com/") == "https://api.deepseek.com"


def test_public_http_is_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("http://api.deepseek.com")


def test_cloud_metadata_address_is_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://169.254.169.254/latest/meta-data", allow_private=True)


def test_loopback_requires_private_flag() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("http://127.0.0.1:11434/v1")
    assert validate_endpoint("http://127.0.0.1:11434/v1", allow_private=True)


def test_localhost_name_requires_private_flag() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("http://localhost:11434/v1")
    assert validate_endpoint("http://localhost:11434/v1", allow_private=True)


def test_private_cidr_requires_private_flag() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://192.168.1.10:8000/v1")
    assert validate_endpoint("https://192.168.1.10:8000/v1", allow_private=True)


def test_userinfo_is_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://user:pass@api.deepseek.com")


def test_decimal_ip_bypass_is_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://2130706433")


def test_hex_ip_bypass_is_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://0x7f.0.0.1")


def test_query_and_fragment_are_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("https://api.deepseek.com?x=1")
    with pytest.raises(InvalidInput):
        validate_endpoint("https://api.deepseek.com#frag")


def test_empty_and_bad_scheme_are_rejected() -> None:
    with pytest.raises(InvalidInput):
        validate_endpoint("")
    with pytest.raises(InvalidInput):
        validate_endpoint("file:///etc/passwd")
