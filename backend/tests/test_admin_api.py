from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.auth import InMemoryAuthRepository
from app.domain.system_settings import InMemorySystemSettingsRepository
from tests.support import build_test_app


def build_client(
    phone: str,
    repo: InMemoryAuthRepository,
    settings_repo: InMemorySystemSettingsRepository,
    *,
    admin_phones: str = "",
) -> TestClient:
    settings = Settings(  # type: ignore[call-arg]
        local_mode=False,
        env="test",
        _env_file=None,
        debug_auth=False,
        sms_debug=True,
        admin_phones=admin_phones,
    )
    # 用共享工厂补齐所有仓储：只传 auth 与 settings 时，其余会去连真实
    # PostgreSQL，在 CI（没有数据库）上就会失败。
    return TestClient(
        build_test_app(
            settings,
            auth_repo=repo,
            system_settings_repo=settings_repo,
        )
    )


def login(test_client: TestClient, phone: str) -> None:
    code_response = test_client.post("/v1/auth/sms-code", json={"phone": phone})
    code = code_response.json()["debug_code"]
    response = test_client.post("/v1/auth/login", json={"phone": phone, "code": code})
    assert response.status_code == 200


def test_admin_can_read_and_update_settings() -> None:
    repo = InMemoryAuthRepository()
    settings_repo = InMemorySystemSettingsRepository()
    admin = build_client("13800001234", repo, settings_repo, admin_phones="13800001234")
    login(admin, "13800001234")

    listing = admin.get("/v1/admin/settings")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["settings"]["quota"]["enforced"] is False
    # 测试环境未配置 Key，可用模型应为空或仅含本地启用项
    assert isinstance(payload["models"], list)

    updated = admin.put(
        "/v1/admin/settings",
        json={
            "quota": {"enforced": True, "daily_limit": 2},
            "model_defaults": {
                "chat_main": {
                    "temperature": 0.3,
                    "max_tokens": 128,
                    "top_p": 0.7,
                    "thinking": True,
                }
            },
        },
    )
    assert updated.status_code == 200
    chat_main = updated.json()["settings"]["model_defaults"]["chat_main"]
    assert chat_main["temperature"] == 0.3
    assert chat_main["top_p"] == 0.7
    assert chat_main["thinking"] is True
    assert updated.json()["settings"]["quota"]["enforced"] is True

    reloaded = admin.get("/v1/admin/settings").json()["settings"]["model_defaults"]["chat_main"]
    assert reloaded["top_p"] == 0.7
    assert reloaded["thinking"] is True

    quota = admin.get("/v1/me/quota").json()
    assert quota["enforced"] is True
    assert quota["limit"] == 2

    audit = admin.get("/v1/admin/audit").json()
    assert audit and audit[0]["action"] == "settings.update"


def test_admin_rejects_invalid_top_p() -> None:
    repo = InMemoryAuthRepository()
    settings_repo = InMemorySystemSettingsRepository()
    admin = build_client("13800001234", repo, settings_repo, admin_phones="13800001234")
    login(admin, "13800001234")
    response = admin.put(
        "/v1/admin/settings",
        json={"model_defaults": {"chat_main": {"top_p": 1.5}}},
    )
    assert response.status_code == 422


def test_normal_user_cannot_access_admin() -> None:
    repo = InMemoryAuthRepository()
    settings_repo = InMemorySystemSettingsRepository()
    user = build_client("13900005678", repo, settings_repo)
    login(user, "13900005678")
    response = user.get("/v1/admin/settings")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FORBIDDEN"


def test_admin_phone_is_promoted_on_login() -> None:
    repo = InMemoryAuthRepository()
    settings_repo = InMemorySystemSettingsRepository()
    admin = build_client("13800001234", repo, settings_repo, admin_phones="13800001234")
    login(admin, "13800001234")
    me = admin.get("/v1/me").json()
    assert me["role"] == "admin"
