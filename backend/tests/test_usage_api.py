import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.usage import CallRecord, InMemoryUsageRepository
from app.main import create_app


def seeded_repo() -> InMemoryUsageRepository:
    repo = InMemoryUsageRepository()
    repo.records.extend(
        [
            CallRecord(
                user_id="u1",
                task="chat_main",
                request_id="r1",
                provider_key="deepseek",
                model_key="deepseek:deepseek-flash",
                prompt_tokens=1000,
                completion_tokens=100,
                cache_hit_tokens=800,
                cache_miss_tokens=200,
                cost_micros=1500,
                first_token_ms=1200,
            ),
            CallRecord(
                user_id="u1",
                task="memory_extract",
                request_id="r2",
                provider_key="deepseek",
                model_key="deepseek:deepseek-flash",
                prompt_tokens=500,
                completion_tokens=50,
                cache_hit_tokens=0,
                cache_miss_tokens=500,
                cost_micros=900,
                first_token_ms=2000,
                status="error",
                error_code="RATE_LIMITED",
            ),
            CallRecord(
                user_id="u2",
                task="chat_main",
                request_id="r3",
                provider_key="deepseek",
                model_key="deepseek:deepseek-v4-pro",
                prompt_tokens=100,
                completion_tokens=10,
                cost_micros=5000,
                first_token_ms=900,
            ),
        ]
    )
    return repo


def client(repo: InMemoryUsageRepository) -> TestClient:
    settings = Settings(local_mode=False, debug_auth=True, env="test", _env_file=None)  # type: ignore[call-arg]
    return TestClient(create_app(settings, usage_repo=repo))


def test_summary_only_counts_current_user() -> None:
    response = client(seeded_repo()).get("/v1/me/usage/models", headers={"X-User-Id": "u1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 7
    assert payload["totals"]["calls"] == 2
    assert payload["totals"]["ok_calls"] == 1
    assert payload["totals"]["input_tokens"] == 1500
    assert payload["totals"]["cache_hit_tokens"] == 800
    assert payload["totals"]["cost_cny"] == pytest.approx(0.0024)
    assert len(payload["by_model"]) == 1
    assert payload["by_model"][0]["model_key"] == "deepseek:deepseek-flash"
    assert payload["by_model"][0]["avg_first_token_ms"] == 1600
    assert payload["by_model"][0]["totals"]["hit_ratio"] == pytest.approx(800 / 1500, abs=1e-4)


def test_days_parameter_is_validated() -> None:
    response = client(seeded_repo()).get("/v1/me/usage/models?days=0", headers={"X-User-Id": "u1"})
    assert response.status_code == 422


def test_summary_returns_empty_for_new_user() -> None:
    response = client(seeded_repo()).get("/v1/me/usage/models", headers={"X-User-Id": "nobody"})
    assert response.status_code == 200
    assert response.json()["totals"]["calls"] == 0


def test_cost_is_rounded_to_six_decimals() -> None:
    payload = client(seeded_repo()).get("/v1/me/usage/models", headers={"X-User-Id": "u2"}).json()
    assert payload["totals"]["cost_cny"] == 0.005
