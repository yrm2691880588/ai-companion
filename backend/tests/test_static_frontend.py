from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def build(tmp_path) -> TestClient:  # type: ignore[no-untyped-def]
    (tmp_path / "index.html").write_text("<html><body>spa</body></html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    app = create_app(
        Settings(env="test", _env_file=None, frontend_dist=str(tmp_path))  # type: ignore[call-arg]
    )
    return TestClient(app)


def test_root_serves_index(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = build(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "spa" in response.text


def test_spa_fallback_for_client_routes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = build(tmp_path)
    response = client.get("/companions/1/chat")
    assert response.status_code == 200
    assert "spa" in response.text


def test_assets_are_served(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = build(tmp_path)
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_unknown_api_returns_404(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = build(tmp_path)
    response = client.get("/v1/does-not-exist")
    assert response.status_code == 404
