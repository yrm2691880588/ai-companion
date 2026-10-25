from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.auth import InMemoryAuthRepository
from app.domain.system_settings import InMemorySystemSettingsRepository
from app.main import create_app


def build_client(
    phone: str,
    repo: InMemoryAuthRepository,
    settings_repo: InMemorySystemSettingsRepository,
    *,
    admin_phones: str = "",
) -> TestClient:
    settings = Settings(  # type: ignore[call-arg]
        env="test",
        _env_file=None,
        debug_auth=False,
        sms_debug=True,
        admin_phones=admin_phones,
    )
    return TestClient(
        create_app(
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
    assert len(payload["models"]) >= 2

    updated = admin.put(
        "/v1/admin/settings",
        json={
            "quota": {"enforced": True, "daily_limit": 2},
            "model_defaults": {"chat_main": {"temperature": 0.3, "max_tokens": 128}},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["settings"]["quota"]["enforced"] is True

    quota = admin.get("/v1/me/quota").json()
    assert quota["enforced"] is True
    assert quota["limit"] == 2

    audit = admin.get("/v1/admin/audit").json()
    assert audit and audit[0]["action"] == "settings.update"


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
