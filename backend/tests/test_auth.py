import pytest

from app.core.errors import AppError, InvalidInput
from app.domain.auth import (
    AuthService,
    InMemoryAuthRepository,
    hash_code,
    mask_phone,
    normalize_phone,
)


def build(**kwargs: object) -> tuple[AuthService, InMemoryAuthRepository]:
    repo = InMemoryAuthRepository()
    service = AuthService(repo, sms_debug=True, **kwargs)  # type: ignore[arg-type]
    return service, repo


def test_phone_normalization_and_mask() -> None:
    assert normalize_phone("138 0000 1234") == "13800001234"
    assert mask_phone("13800001234") == "138****1234"
    with pytest.raises(InvalidInput):
        normalize_phone("12345")
    with pytest.raises(InvalidInput):
        normalize_phone("23800001234")


async def test_request_code_and_login_creates_account() -> None:
    service, repo = build()
    code, _expires = await service.request_code("13800001234")
    assert len(code) == 6

    token, account, _expires_at = await service.login("13800001234", code)
    assert account.phone == "13800001234"
    assert await service.resolve_account_id(token) == account.id
    assert len(repo.accounts) == 1

    # 同一验证码不能复用
    with pytest.raises(AppError):
        await service.login("13800001234", code)


async def test_resend_is_rate_limited() -> None:
    service, _ = build()
    await service.request_code("13800001234")
    with pytest.raises(AppError) as excinfo:
        await service.request_code("13800001234")
    assert excinfo.value.code == "SMS_TOO_FREQUENT"
    assert excinfo.value.status_code == 429


async def test_wrong_code_increments_attempts_and_locks() -> None:
    service, repo = build()
    code, _ = await service.request_code("13800001234")
    record = repo.codes[-1]
    for _ in range(5):
        with pytest.raises(AppError):
            await service.login("13800001234", "000000" if code != "000000" else "111111")
    assert repo.codes[-1].attempts == 5
    with pytest.raises(AppError) as excinfo:
        await service.login("13800001234", code)
    assert excinfo.value.code == "CODE_LOCKED"
    assert repo.codes[-1].id == record.id


async def test_expired_code_is_rejected() -> None:
    service, _ = build(code_ttl_seconds=-1)
    code, _ = await service.request_code("13800001234")
    with pytest.raises(AppError) as excinfo:
        await service.login("13800001234", code)
    assert excinfo.value.code == "CODE_EXPIRED"


async def test_logout_revokes_session() -> None:
    service, _ = build()
    code, _ = await service.request_code("13800001234")
    token, _account, _ = await service.login("13800001234", code)
    await service.logout(token)
    assert await service.resolve_account_id(token) is None


async def test_code_hash_is_not_plaintext() -> None:
    digest = hash_code("13800001234", "123456")
    assert digest != "123456"
    assert len(digest) == 64
