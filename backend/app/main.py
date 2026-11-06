"""FastAPI 应用入口：模型层、人设与伴侣、模板、用量统计与健康检查。"""

from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import me_router as me_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.companion_batch import router as companion_batch_router
from app.api.v1.companions import router as companions_router
from app.api.v1.device import router as device_router
from app.api.v1.export import router as export_router
from app.api.v1.import_data import router as import_router
from app.api.v1.memories import router as memories_router
from app.api.v1.models import router as models_router
from app.api.v1.persona_transfer import router as persona_transfer_router
from app.api.v1.personas import router as personas_router
from app.api.v1.provider_settings import router as provider_settings_router
from app.api.v1.quota import router as quota_router
from app.api.v1.roleplay import router as roleplay_router
from app.api.v1.system import router as system_router
from app.api.v1.templates import router as templates_router
from app.api.v1.trial import router as trial_router
from app.api.v1.usage import router as usage_router
from app.api.v1.user_profile import router as user_profile_router
from app.api.v1.voice import router as voice_router
from app.core.config import Settings, get_settings
from app.core.device import DEVICE_HEADER, device_scope
from app.core.errors import AppError
from app.core.logging_setup import resolve_log_dir, setup_file_logging
from app.core.version import app_version
from app.domain.auth import AuthRepository, AuthService
from app.domain.chat import ChatRepository, ChatService, ChatStreamer
from app.domain.companions import CompanionRepository, CompanionService, LLMClient
from app.domain.custom_models import (
    InMemoryCustomModelRepository,
    SqlCustomModelRepository,
)
from app.domain.deletion import DeletionRepository, DeletionService
from app.domain.memory import MemoryRepository, MemoryService
from app.domain.provider_settings import (
    InMemoryProviderSettingsRepository,
    ProviderSettingsService,
)
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
from app.domain.voice import (
    InMemoryVoiceSettingsRepository,
    InMemoryVoiceUsageRepository,
    InMemoryVoiceVoiceRepository,
    VoiceService,
)
from app.infra.analytics_repo import InMemoryAnalyticsRepository, SqlAnalyticsRepository
from app.infra.audio_store import AudioStore
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
from app.infra.provider_settings_repo import SqlProviderSettingsRepository
from app.infra.quota_repo import SqlQuotaRepository
from app.infra.roleplay_repo import SqlRunRepository, SqlSafetyRepository, SqlScenarioRepository
from app.infra.summary_repo import SqlSummaryRepository, SummaryRepository
from app.infra.system_settings_repo import SqlSystemSettingsRepository
from app.infra.template_repo import SqlTemplateRepository
from app.infra.usage_repo import SqlUsageRepository
from app.infra.user_profile_repo import SqlUserProfileRepository
from app.infra.voice.registry import VoiceProviderRegistry
from app.infra.voice_repo import (
    SqlVoiceSettingsRepository,
    SqlVoiceUsageRepository,
    SqlVoiceVoiceRepository,
)
from app.security.crypto import SecretBox

_LOG = logging.getLogger(__name__)


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


def _secret_box(settings: Settings) -> SecretBox | None:
    """主密钥可用时返回加密盒；未配置则返回 None（Key 不落库）。"""
    raw = settings.master_key
    if not raw:
        return None
    try:
        return SecretBox(raw)
    except Exception:
        return None


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
    log_path = setup_file_logging(
        resolve_log_dir(str(getattr(resolved, "log_dir", "") or "")),
        level=getattr(logging, str(resolved.log_level).upper(), logging.INFO),
    )
    if log_path is not None:
        _LOG.info("错误日志写入 %s", log_path)
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
    provider_settings_store = (
        InMemoryProviderSettingsRepository()
        if resolved.env == "test"
        else SqlProviderSettingsRepository(session_factory, _secret_box(resolved))
    )
    provider_settings_service = ProviderSettingsService(
        provider_settings_store,
        known_providers=set(registry.providers),
    )
    custom_model_repo = (
        InMemoryCustomModelRepository()
        if resolved.env == "test"
        else SqlCustomModelRepository(session_factory)
    )
    box = _secret_box(resolved)
    voice_registry = VoiceProviderRegistry(
        tts_resource_id=resolved.voice_tts_resource_id,
        asr_resource_id=resolved.voice_asr_resource_id,
    )
    if resolved.env == "test":
        voice_settings_store = InMemoryVoiceSettingsRepository()
        voice_voices_store = InMemoryVoiceVoiceRepository()
        voice_usage_store = InMemoryVoiceUsageRepository()
    else:
        voice_settings_store = SqlVoiceSettingsRepository(session_factory, box)
        voice_voices_store = SqlVoiceVoiceRepository(session_factory)
        voice_usage_store = SqlVoiceUsageRepository(session_factory)
    voice_service = VoiceService(
        voice_registry,
        voice_settings_store,
        voice_voices_store,
        voice_usage_store,
        box=box,
    )
    audio_root = (
        Path(resolved.audio_dir)
        if getattr(resolved, "audio_dir", "")
        else Path(tempfile.gettempdir()) / "ai-companion-audio"
    )
    audio_store = AudioStore(audio_root)
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
        await app.state.apply_provider_settings()
        yield
        await engine.dispose()

    app = FastAPI(title="AI 伴侣系统 API", version=app_version(), lifespan=lifespan)
    # 跨端访问：手机/PWA 直连本机后端时需要 CORS；默认只允许同源
    if resolved.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 设备标识：写入数据时记录来源设备，便于跨端冲突判定
    @app.middleware("http")
    async def _attach_device(request: Request, call_next: Any) -> Any:
        with device_scope(request.headers.get(DEVICE_HEADER)):
            return await call_next(request)

    app.state.settings = resolved
    app.state.registry = registry
    app.state.provider_settings_service = provider_settings_service
    app.state.custom_model_repo = custom_model_repo
    app.state.voice_service = voice_service
    app.state.audio_store = audio_store

    async def apply_provider_settings() -> None:
        """把库里的供应商 Key/URL 合并进注册表，并让路由使用新注册表。"""
        stored = await provider_settings_service.load()
        keys = dict(resolved.provider_keys())
        for key, setting in stored.items():
            if setting.api_key:
                keys[key] = setting.api_key
        updated = registry.with_keys(keys)
        stored_models = await custom_model_repo.all()
        if stored_models:
            from app.infra.llm.pricing import parse_banded_price
            from app.infra.llm.types import Capability, ModelSpec

            zero = parse_banded_price(
                {
                    "hit": {"peak": 0.0, "offpeak": 0.0},
                    "miss": {"peak": 0.0, "offpeak": 0.0},
                    "out": {"peak": 0.0, "offpeak": 0.0},
                }
            )
            specs = [
                ModelSpec(
                    key=f"{item.provider_key}:{item.model_name}",
                    provider_key=item.provider_key,
                    model_name=item.model_name,
                    display_name=item.display_name,
                    context_window=item.context_window,
                    max_output=item.max_output,
                    supports=frozenset({Capability.STREAM}),
                    price=zero,
                    notes="用户导入的模型",
                )
                for item in stored_models
            ]
            updated = updated.with_extra_models(specs)
        app.state.registry = updated
        router.registry = updated
        client.registry = updated  # type: ignore[attr-defined]

    app.state.apply_provider_settings = apply_provider_settings
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

    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        """兜底：记录完整堆栈到日志，对外只回通用错误，不泄露内部细节。"""
        _LOG.error(
            "未处理异常 path=%s method=%s",
            request.url.path,
            request.method,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误，请查看日志",
                "details": {},
            },
        )

    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)  # type: ignore[arg-type]
    app.include_router(models_router)
    app.include_router(usage_router)
    app.include_router(personas_router)
    app.include_router(provider_settings_router)
    app.include_router(persona_transfer_router)
    app.include_router(companion_batch_router)
    app.include_router(companions_router)
    app.include_router(system_router)
    app.include_router(templates_router)
    app.include_router(trial_router)
    app.include_router(analytics_router)
    app.include_router(user_profile_router)
    app.include_router(voice_router)
    app.include_router(roleplay_router)
    app.include_router(quota_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(device_router)
    app.include_router(export_router)
    app.include_router(import_router)
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


# 静态资源 MIME：Python 默认表缺 .mjs / .wasm，浏览器会拒绝加载 ES 模块
_STATIC_MEDIA_TYPES = {
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".wasm": "application/wasm",
    ".onnx": "application/octet-stream",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
}


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
            # .mjs 必须回 text/javascript，否则浏览器拒绝当 ES 模块加载
            # （VAD 的 onnxruntime wasm 加载器就是 .mjs，漏了会直接报
            #  "Failed to fetch dynamically imported module"）
            media_type = _STATIC_MEDIA_TYPES.get(candidate.suffix.lower())
            return FileResponse(candidate, media_type=media_type)
        if full_path and candidate.suffix:
            raise AppError(code="NOT_FOUND", message="文件不存在", status_code=404)
        return FileResponse(index)


app = create_app()
