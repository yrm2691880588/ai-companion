"""语音配置接口：供应商、凭据、探活、音色列表。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id, require_admin
from app.core.errors import AppError
from app.domain.voice import VoiceService
from app.infra.audio_store import AudioStore

router = APIRouter(prefix="/v1/voice", tags=["voice"])


class VoiceProviderOut(BaseModel):
    key: str
    display_name: str
    supports_cloning: bool = False
    configured: bool = False
    enabled: bool = True
    app_id: str = ""


class VoiceProviderPatchIn(BaseModel):
    app_id: str | None = Field(default=None, max_length=128)
    token: str | None = Field(default=None, max_length=512)
    cluster: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class VoiceOptionOut(BaseModel):
    voice_id: str
    display_name: str
    gender: str = ""
    tags: list[str] = Field(default_factory=list)
    params_schema: dict[str, object] = Field(default_factory=dict)


def get_service(request: Request) -> VoiceService:
    service = getattr(request.app.state, "voice_service", None)
    if not isinstance(service, VoiceService):
        raise AppError(code="VOICE_UNAVAILABLE", message="语音服务未初始化", status_code=503)
    return service


ServiceDep = Annotated[VoiceService, Depends(get_service)]
AdminDep = Annotated[str, Depends(require_admin)]


@router.get("/providers", response_model=list[VoiceProviderOut])
async def list_providers(_admin: AdminDep, service: ServiceDep) -> list[VoiceProviderOut]:
    return [VoiceProviderOut(**item) for item in await service.list_providers()]


@router.put("/providers/{provider_key}", response_model=VoiceProviderOut)
async def update_provider(
    provider_key: str,
    payload: VoiceProviderPatchIn,
    _admin: AdminDep,
    service: ServiceDep,
) -> VoiceProviderOut:
    await service.update(
        provider_key,
        app_id=payload.app_id,
        token=payload.token,
        cluster=payload.cluster,
        base_url=payload.base_url,
        enabled=payload.enabled,
    )
    for item in await service.list_providers():
        if item["key"] == provider_key:
            return VoiceProviderOut(**item)
    raise AppError(code="VOICE_PROVIDER_NOT_FOUND", message="语音供应商不存在", status_code=404)


@router.post("/providers/{provider_key}/probe")
async def probe_provider(
    provider_key: str, _admin: AdminDep, service: ServiceDep
) -> dict[str, object]:
    result = await service.probe(provider_key)
    return {"provider_key": provider_key, **result}


@router.get("/providers/{provider_key}/voices", response_model=list[VoiceOptionOut])
async def list_voices(
    provider_key: str,
    _admin: AdminDep,
    service: ServiceDep,
    refresh: bool = False,
) -> list[VoiceOptionOut]:
    voices = await service.list_voices(provider_key, refresh=refresh)
    return [
        VoiceOptionOut(
            voice_id=voice.voice_id,
            display_name=voice.display_name,
            gender=voice.gender,
            tags=voice.tags,
            params_schema=voice.params_schema,
        )
        for voice in voices
    ]


class TranscribeOut(BaseModel):
    text: str
    duration_ms: int = 0


class SynthesizeIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_id: str = Field(min_length=1, max_length=128)
    params: dict[str, object] | None = None
    provider_key: str = "volcengine"
    session_id: int | None = None


class SynthesizeOut(BaseModel):
    audio_url: str
    expires_in: int


def get_audio_store(request: Request) -> AudioStore:
    store = getattr(request.app.state, "audio_store", None)
    if not isinstance(store, AudioStore):
        raise AppError(code="VOICE_UNAVAILABLE", message="音频存储未初始化", status_code=503)
    return store


StoreDep = Annotated[AudioStore, Depends(get_audio_store)]
UserDep = Annotated[str, Depends(get_current_user_id)]
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    request: Request,
    user_id: UserDep,
    service: ServiceDep,
    file: UploadFile = File(...),
    provider_key: str = "volcengine",
) -> TranscribeOut:
    """上传录音，返回识别文字。"""
    audio = await file.read()
    if len(audio) > MAX_AUDIO_BYTES:
        raise AppError(code="VOICE_AUDIO_TOO_LARGE", message="音频超过 10MB", status_code=413)
    content_type = file.content_type or "audio/webm"
    result = await service.transcribe(provider_key, audio, content_type, user_id=user_id)
    return TranscribeOut(text=result.text, duration_ms=result.duration_ms)


@router.post("/synthesize", response_model=SynthesizeOut)
async def synthesize(
    payload: SynthesizeIn,
    user_id: UserDep,
    service: ServiceDep,
    store: StoreDep,
) -> SynthesizeOut:
    """把伴侣回复合成语音，返回短期可播地址。"""
    speech = await service.synthesize(
        payload.provider_key,
        payload.text,
        payload.voice_id,
        payload.params,
        user_id=user_id,
        session_id=payload.session_id,
    )
    suffix = ".mp3" if "mpeg" in speech.content_type else ".bin"
    audio_id = store.save(speech.audio, suffix=suffix)
    return SynthesizeOut(
        audio_url=f"/v1/voice/audio/{audio_id}",
        expires_in=store.ttl_seconds,
    )


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str, store: StoreDep) -> FileResponse:
    path = store.path_for(audio_id)
    if path is None:
        raise AppError(
            code="VOICE_AUDIO_EXPIRED", message="音频已过期，请重新生成", status_code=410
        )
    media_type = "audio/mpeg" if path.suffix == ".mp3" else "application/octet-stream"
    return FileResponse(path, media_type=media_type)
