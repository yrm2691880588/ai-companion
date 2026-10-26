from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.auth import InMemoryAuthRepository
from app.main import create_app


def client(
    auth_repo: InMemoryAuthRepository | None = None, **settings_kwargs: object
) -> TestClient:
    values: dict[str, object] = {
        "local_mode": False,
        "env": "test",
        "_env_file": None,
        "debug_auth": False,
        "sms_debug": True,
    }
    values.update(settings_kwargs)
    settings = Settings(**values)  # type: ignore[arg-type]
    app = create_app(settings, auth_repo=auth_repo or InMemoryAuthRepository())
    return TestClient(app)


def login(test_client: TestClient, phone: str = "13800001234") -> dict[str, object]:
    code_response = test_client.post("/v1/auth/sms-code", json={"phone": phone})
    assert code_response.status_code == 200
    code = code_response.json()["debug_code"]
    assert code
    response = test_client.post("/v1/auth/login", json={"phone": phone, "code": code})
    assert response.status_code == 200
    return response.json()


def test_login_sets_cookie_and_me_works() -> None:
    test_client = client()
    payload = login(test_client)
    assert payload["phone_masked"] == "138****1234"

    me = test_client.get("/v1/me")
    assert me.status_code == 200
    assert me.json()["phone_masked"] == "138****1234"
    assert me.json()["account_id"] == payload["account_id"]


def test_header_is_rejected_when_auth_required() -> None:
    test_client = client()
    response = test_client.get("/v1/companions", headers={"X-User-Id": "dev-user"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHORIZED"


def test_logout_clears_session() -> None:
    test_client = client()
    login(test_client)
    assert test_client.post("/v1/auth/logout").status_code == 200
    response = test_client.get("/v1/me")
    assert response.status_code == 401


def test_wrong_code_is_rejected() -> None:
    test_client = client()
    code_response = test_client.post("/v1/auth/sms-code", json={"phone": "13800001234"})
    code = code_response.json()["debug_code"]
    wrong = "000000" if code != "000000" else "111111"
    response = test_client.post("/v1/auth/login", json={"phone": "13800001234", "code": wrong})
    assert response.status_code == 401
    assert response.json()["code"] == "CODE_INVALID"


def test_sms_code_not_returned_when_debug_off() -> None:
    test_client = client(sms_debug=False)
    response = test_client.post("/v1/auth/sms-code", json={"phone": "13800001234"})
    assert response.status_code == 200
    assert response.json()["debug_code"] is None


def test_sessions_are_isolated_between_accounts() -> None:
    repo = InMemoryAuthRepository()
    alice = client(repo)
    bob = client(repo)
    login(alice, "13800001234")
    login(bob, "13900005678")

    assert alice.get("/v1/me").json()["phone_masked"] == "138****1234"
    assert bob.get("/v1/me").json()["phone_masked"] == "139****5678"
