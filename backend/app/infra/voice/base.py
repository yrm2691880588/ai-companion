"""语音供应商抽象：业务只认识这个协议，不认识具体厂商。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.errors import AppError


@dataclass(slots=True)
class VoiceCredential:
    """供应商凭据；字段按供应商不同，统一放 dict。"""

    app_id: str = ""
    token: str = ""
    cluster: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.token)


@dataclass(slots=True)
class VoiceOption:
    voice_id: str
    display_name: str
    gender: str = ""
    tags: list[str] = field(default_factory=list)
    params_schema: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Transcript:
    text: str
    duration_ms: int = 0


@dataclass(slots=True)
class Speech:
    audio: bytes
    content_type: str = "audio/mpeg"
    duration_ms: int = 0


class VoiceProvider(Protocol):
    key: str
    display_name: str

    def supports_cloning(self) -> bool: ...

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]: ...

    async def transcribe(
        self, credential: VoiceCredential, audio: bytes, content_type: str
    ) -> Transcript: ...

    async def synthesize(
        self,
        credential: VoiceCredential,
        text: str,
        voice_id: str,
        params: dict[str, object] | None = None,
    ) -> Speech: ...

    async def probe(self, credential: VoiceCredential) -> dict[str, object]: ...


class VoiceError(AppError):
    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(code=code, message=message, status_code=status_code)
