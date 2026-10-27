"""火山引擎语音适配（豆包语音）。

说明：不同产品线的鉴权头与接口路径不同，这里把火山细节全部收敛在本文件，
业务层只使用 VoiceProvider 协议。
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import httpx

from app.infra.voice.base import (
    Speech,
    Transcript,
    VoiceCredential,
    VoiceError,
    VoiceOption,
)

DEFAULT_BASE = "https://openspeech.bytedance.com"

# 火山内置音色（示例集合，可用 /voices 刷新覆盖；voice_id 为火山的 voice_type）
BUILTIN_VOICES = [
    VoiceOption("BV700_streaming", "通用女声", "女", ["通用", "温柔"]),
    VoiceOption("BV001_streaming", "通用男声", "男", ["通用", "沉稳"]),
    VoiceOption("BV005_streaming", "活泼女声", "女", ["活泼", "年轻"]),
    VoiceOption("BV002_streaming", "成熟男声", "男", ["成熟", "低沉"]),
    VoiceOption("BV419_streaming", "甜美少女", "女", ["甜美", "年轻"]),
]


class VolcengineVoiceProvider:
    key = "volcengine"
    display_name = "火山引擎（豆包语音）"

    def __init__(self, *, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        self._timeout = timeout

    def supports_cloning(self) -> bool:
        # 火山支持声音复刻，但本期不实现，只声明能力供前端置灰提示
        return True

    def _headers(self, credential: VoiceCredential) -> dict[str, str]:
        if not credential.configured:
            raise VoiceError(
                "VOICE_NO_CREDENTIAL", "请先配置 AppID 与 Access Token", status_code=400
            )
        headers = {
            "Authorization": f"Bearer; {credential.token}",
            "Content-Type": "application/json",
        }
        if credential.app_id:
            headers["X-Api-App-Id"] = credential.app_id
        if credential.cluster:
            headers["X-Api-Cluster"] = credential.cluster
        return headers

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        # 火山没有统一的公开音色列表接口，先用内置清单；有企业接口时在此替换
        self._headers(credential)
        return list(BUILTIN_VOICES)

    async def transcribe(
        self, credential: VoiceCredential, audio: bytes, content_type: str
    ) -> Transcript:
        headers = self._headers(credential)
        payload = {
            "user": {"uid": credential.app_id or "local"},
            "audio": {
                "format": "wav" if "wav" in content_type else "ogg",
                "data": base64.b64encode(audio).decode("ascii"),
            },
            "request": {"model_name": "bigmodel", "enable_itn": True},
        }
        url = f"{self._base}/api/v3/asr/sauc/bigmodel/recognize/flash"
        data = await self._post(url, headers, payload, "识别")
        try:
            text = (
                data.get("result", {}).get("text")
                or data.get("result", {}).get("utterances", [{}])[0].get("text")
                or ""
            )
        except (AttributeError, IndexError, TypeError):
            text = ""
        if not text:
            raise VoiceError("VOICE_ASR_EMPTY", "没有识别到内容，请再说一次")
        duration = int(data.get("audio_info", {}).get("duration", 0) or 0)
        return Transcript(text=text.strip(), duration_ms=duration)

    async def synthesize(
        self,
        credential: VoiceCredential,
        text: str,
        voice_id: str,
        params: dict[str, object] | None = None,
    ) -> Speech:
        headers = self._headers(credential)
        headers["Content-Type"] = "application/json"
        settings = {
            "speech_rate": int((params or {}).get("speed", 0) or 0),
            "loudness_rate": int((params or {}).get("volume", 0) or 0),
            "pitch_rate": int((params or {}).get("pitch", 0) or 0),
        }
        payload: dict[str, Any] = {
            "user": {"uid": credential.app_id or "local"},
            "req_params": {
                "text": text,
                "speaker": voice_id,
                "audio_params": {"format": "mp3", "sample_rate": 24000, **settings},
            },
        }
        url = f"{self._base}/api/v1/tts"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise VoiceError("VOICE_TTS_UNREACHABLE", f"合成服务无法连接：{exc}") from exc
        if response.status_code >= 400:
            raise VoiceError(
                "VOICE_TTS_ERROR", f"合成失败（{response.status_code}）：{response.text[:120]}"
            )
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = response.json()
                audio_b64 = data.get("data")
                if not audio_b64:
                    raise VoiceError("VOICE_TTS_EMPTY", "合成没有返回音频")
                return Speech(audio=base64.b64decode(audio_b64), content_type="audio/mpeg")
            except (ValueError, TypeError) as exc:
                raise VoiceError("VOICE_TTS_BAD_RESPONSE", "合成返回格式异常") from exc
        return Speech(audio=response.content, content_type=content_type or "audio/mpeg")

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        voices = await self.list_voices(credential)
        return {"ok": True, "voice_count": len(voices)}

    async def _post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        action: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    params={"request_id": str(uuid.uuid4())},
                )
            except httpx.HTTPError as exc:
                raise VoiceError("VOICE_UNREACHABLE", f"{action}服务无法连接：{exc}") from exc
        if response.status_code in (401, 403):
            raise VoiceError("VOICE_AUTH_ERROR", "AppID 或 Token 无效", status_code=400)
        if response.status_code == 429:
            raise VoiceError("VOICE_RATE_LIMITED", "触发限流，请稍后再试", status_code=429)
        if response.status_code >= 400:
            raise VoiceError(
                "VOICE_UPSTREAM_ERROR",
                f"{action}失败（{response.status_code}）：{response.text[:120]}",
            )
        try:
            return response.json()
        except ValueError as exc:
            raise VoiceError("VOICE_BAD_RESPONSE", f"{action}返回的不是 JSON") from exc
