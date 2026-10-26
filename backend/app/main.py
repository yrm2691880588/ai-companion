"""FastAPI 应用入口：模型层、人设与伴侣、模板、用量统计与健康检查。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import me_router as me_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.companions import router as companions_router
from app.api.v1.export import router as export_router
from app.api.v1.memories import router as memories_router
from app.api.v1.models import router as models_router
from app.api.v1.persona_transfer import router as persona_transfer_router
from app.api.v1.personas import router as personas_router
from app.api.v1.quota import router as quota_router
from app.api.v1.roleplay import router as roleplay_router
from app.api.v1.templates import router as templates_router
from app.api.v1.trial import router as trial_router
from app.api.v1.usage import router as usage_router
from app.api.v1.user_profile import router as user_profile_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domain.auth import AuthRepository, AuthService
from app.domain.chat import ChatRepository, ChatService, ChatStreamer
from app.domain.companions import CompanionRepository, CompanionService, LLMClient
from app.domain.deletion import DeletionRepository, DeletionService
from app.domain.memory import MemoryRepository, MemoryService
from app.domain.quota import QuotaRepository, QuotaService
from app.domain.roleplay import SCENARIOS, RoleplayService, RunRepository, ScenarioRepository
from app.domain.safety import SafetyEventRepository
from app.domain.system_settings import (
    InMemorySystemSettingsRepository,
    SystemSettingsRepository,
    SystemSettingsService,
)
from app.domain.templates import TEMPLATES, TemplateRepository
from app.domain.trial import TrialService
from app.domain.usage import UsageRepository
from app.domain.user_profile import InMemoryUserProfileRepository, UserProfileService
from app.infra.analytics_repo import InMemoryAnalyticsRepository, SqlAnalyticsRepository
from app.infra.auth_repo import SqlAuthRepository
from app.infra.chat_repo import SqlChatRepository
from app.infra.companion_repo import SqlCompanionRepository
from app.infra.db import build_engine, build_session_factory
from app.infra.deletion_repo import SqlDeletionRepository
from app.infra.llm.client import RouterLLMClient
from app.infra.llm.gateway import LLMGateway
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.router import ModelRouter
from app.infra.memory_repo import SqlMemoryRepository
from app.infra.quota_repo import SqlQuotaRepository
from app.infra.roleplay_repo import SqlRunRepository, SqlSafetyRepository, SqlScenarioRepository
from app.infra.summary_repo import SqlSummaryRepository, SummaryRepository
from app.infra.system_settings_repo import SqlSystemSettingsRepository
from app.infra.template_repo import SqlTemplateRepository
from app.infra.usage_repo import SqlUsageRepository
from app.infra.user_profile_repo import SqlUserProfileRepository

_LOG = logging.getLogger(__name__)


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


def create_app(
    settings: Settings | None = None,
    usage_repo: UsageRepository | None = None,
    companion_repo: CompanionRepository | None = None,
    llm_client: LLMClient | None = None,
    template_repo: TemplateRepository | None = None,
    chat_repo: ChatRepository | None = None,
    chat_streamer: ChatStreamer | None = None,
    memory_repo: MemoryRepository | None = None,
    summary_repo: SummaryRepository | None = None,
    scenario_repo: ScenarioRepository | None = None,
    run_repo: RunRepository | None = None,
    safety_repo: SafetyEventRepository | None = None,
    quota_repo: QuotaRepository | None = None,
    auth_repo: AuthRepository | None = None,
    analytics_repo: object | None = None,
    deletion_repo: DeletionRepository | None = None,
    system_settings_repo: SystemSettingsRepository | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    registry = ModelRegistry.from_presets(keys=resolved.provider_keys())

    engine = build_engine(resolved.database_url)
    session_factory = build_session_factory(engine)
    usage_store: UsageRepository = usage_repo or SqlUsageRepository(session_factory)
    companions_store: CompanionRepository = companion_repo or SqlCompanionRepository(
        session_factory
    )
    templates_store: TemplateRepository = template_repo or SqlTemplateRepository(session_factory)
    chats_store: ChatRepository = chat_repo or SqlChatRepository(session_factory)
    memories_store: MemoryRepository = memory_repo or SqlMemoryRepository(session_factory)
    summaries_store: SummaryRepository = summary_repo or SqlSummaryRepository(session_factory)
    scenarios_store: ScenarioRepository = scenario_repo or SqlScenarioRepository(session_factory)
    runs_store: RunRepository = run_repo or SqlRunRepository(session_factory)
    safety_store: SafetyEventRepository = safety_repo or SqlSafetyRepository(session_factory)
    quotas_store: QuotaRepository = quota_repo or SqlQuotaRepository(session_factory)
    settings_store: SystemSettingsRepository = system_settings_repo or (
        InMemorySystemSettingsRepository()
        if resolved.env == "test"
        else SqlSystemSettingsRepository(session_factory)
    )
    system_settings = SystemSettingsService(settings_store)
    quota_enforced, quota_limit = system_settings.quota_config()
    quota_service = QuotaService(quotas_store, daily_limit=quota_limit, enforced=quota_enforced)
    auth_store: AuthRepository = auth_repo or SqlAuthRepository(session_factory)
    auth_service = AuthService(
        auth_store,
        sms_debug=resolved.sms_debug,
        session_days=resolved.session_days,
        admin_phones=resolved.admin_phone_set,
    )
    deletions_store: DeletionRepository = deletion_repo or SqlDeletionRepository(session_factory)
    deletion_service = DeletionService(deletions_store)
    router = ModelRouter(
        registry,
        LLMGateway(timeout_seconds=120),
        turn_cost_cap_cny=resolved.turn_cost_cap_cny,
        hit_ratio=resolved.default_hit_ratio,
        expected_output_tokens=resolved.expected_output_tokens,
        max_context_ratio=resolved.max_context_ratio,
        recorder=usage_store,
        overrides=system_settings.model_override,
    )
    client: LLMClient = llm_client or RouterLLMClient(router, registry)
    companion_service = CompanionService(companions_store, client, templates_store)
    memory_service = MemoryService(memories_store, client)
    streamer: ChatStreamer = chat_streamer or router
    profile_repo = (
        InMemoryUserProfileRepository()
        if resolved.env == "test"
        else SqlUserProfileRepository(session_factory)
    )
    profile_service = UserProfileService(profile_repo)
    trial_service = TrialService(streamer, profiles=profile_service)
    analytics_repo = analytics_repo or (  # type: ignore[assignment]
        InMemoryAnalyticsRepository()
        if resolved.env == "test"
        else SqlAnalyticsRepository(session_factory)
    )
    chat_service = ChatService(
        chats_store,
        companion_service,
        streamer,
        memory_service,
        summaries_store,
        client,
        resolved.chat_context_budget_tokens,
        safety_store,
        quota_service,
        profile_service,
    )
    roleplay_service = RoleplayService(
        scenarios_store,
        runs_store,
        chats_store,
        companion_service,
        streamer,
        client,
        quota=quota_service,
        profiles=profile_service,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        app.state.started = True
        try:
            await templates_store.sync(TEMPLATES)
            await scenarios_store.sync(SCENARIOS)
        except Exception:  # 数据库未就绪时不要让应用起不来
            _LOG.warning("官方模板/演练场景同步失败（可稍后重试）", exc_info=True)
        try:
            await system_settings.load()
            enforced, limit = system_settings.quota_config()
            quota_service.configure(enforced=enforced, daily_limit=limit)
        except Exception:
            _LOG.warning("系统设置加载失败，使用默认值", exc_info=True)
        yield
        await engine.dispose()

    app = FastAPI(title="AI 伴侣系统 API", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.registry = registry
    app.state.db_engine = engine
    app.state.session_factory = session_factory
    app.state.usage_repo = usage_store
    app.state.companion_repo = companions_store
    app.state.template_repo = templates_store
    app.state.chat_repo = chats_store
    app.state.model_router = router
    app.state.llm_client = client
    app.state.companion_service = companion_service
    app.state.chat_service = chat_service
    app.state.memory_service = memory_service
    app.state.summary_repo = summaries_store
    app.state.roleplay_service = roleplay_service
    app.state.safety_repo = safety_store
    app.state.quota_service = quota_service
    app.state.auth_service = auth_service
    app.state.deletion_service = deletion_service
    app.state.system_settings = system_settings
    app.state.trial_service = trial_service
    app.state.analytics_repo = analytics_repo
    app.state.user_profile_service = profile_service
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.include_router(models_router)
    app.include_router(usage_router)
    app.include_router(personas_router)
    app.include_router(persona_transfer_router)
    app.include_router(companions_router)
    app.include_router(templates_router)
    app.include_router(trial_router)
    app.include_router(analytics_router)
    app.include_router(user_profile_router)
    app.include_router(roleplay_router)
    app.include_router(quota_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(export_router)
    app.include_router(admin_router)
    app.include_router(chat_router)
    app.include_router(memories_router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    async def readyz() -> dict[str, Any]:
        return {
            "status": "ok" if registry.providers else "degraded",
            "providers": len(registry.providers),
            "models": len(registry.models),
            "db_configured": bool(resolved.database_url),
            "env": resolved.env,
        }

    _mount_frontend(app, resolved.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist_setting: str) -> None:
    """有构建产物时，由后端直接托管前端，双击启动只需一个进程。"""
    dist = (
        Path(dist_setting)
        if dist_setting
        else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    index = dist / "index.html"
    if not index.is_file():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path == "v1" or full_path.startswith("v1/"):
            raise AppError(code="NOT_FOUND", message="接口不存在", status_code=404)
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if full_path and candidate.suffix:
            raise AppError(code="NOT_FOUND", message="文件不存在", status_code=404)
        return FileResponse(index)


app = create_app()


