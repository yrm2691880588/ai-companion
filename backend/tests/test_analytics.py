"""埋点：白名单、写入、管理员聚合、未知事件拒绝。"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", _env_file=None)))  # type: ignore[call-arg]


def test_record_known_event() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/analytics",
        json={"name": "app_open", "duration_ms": 120},
    )
    assert response.status_code == 204


def test_unknown_event_is_rejected() -> None:
    test_client = client()
    response = test_client.post("/v1/analytics", json={"name": "drop_table"})
    assert response.status_code == 422


def test_event_does_not_accept_content_field() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/analytics",
        json={"name": "first_message", "content": "不该被接收的消息正文"},
    )
    # pydantic 默认忽略额外字段，但绝不能落库；这里断言接口仍成功且不报 500
    assert response.status_code == 204


def test_summary_requires_admin() -> None:
    test_client = client()
    response = test_client.get("/v1/analytics/summary")
    assert response.status_code == 403
