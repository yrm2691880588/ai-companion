"""火山引擎语音适配（豆包语音 v1 接口）。

真实接口格式（2026-10 实测确认）：
- 合成：POST /api/v1/tts
- 识别：POST /api/v1/asr
- 凭据放在请求体 app 字段（appid / token / cluster），同时需要 Authorization 头
- 缺少 Authorization 时返回 401 "missing Authorization header"

本文件是唯一出现火山专有字段的地方，业务层只认 VoiceProvider 协议。
"""

from __future__ import annotations

import base64
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
TTS_CLUSTER = "volcano_tts"
ASR_CLUSTER = "volcengine_input_common"

# 火山内置音色（voice_type）；有企业接口时可替换为动态拉取
BUILTIN_VOICES = [
    VoiceOption(
        "BV700_streaming", "通用女声", "女", ["通用", "温柔"], {"speed": True, "pitch": True}
    ),
    VoiceOption(
        "BV001_streaming", "通用男声", "男", ["通用", "沉稳"], {"speed": True, "pitch": True}
    ),
    VoiceOption(
        "BV005_streaming", "活泼女声", "女", ["活泼", "年轻"], {"speed": True, "pitch": True}
    ),
    VoiceOption(
        "BV002_streaming", "成熟男声", "男", ["成熟", "低沉"], {"speed": True, "pitch": True}
    ),
    VoiceOption(
        "BV419_streaming", "甜美少女", "女", ["甜美", "年轻"], {"speed": True, "pitch": True}
    ),
    VoiceOption(
        "BV119_streaming", "温柔女声", "女", ["温柔", "治愈"], {"speed": True, "pitch": True}
    ),
]


class VolcengineVoiceProvider:
    key = "volcengine"
    display_name = "火山引擎（豆包语音）"

    def __init__(self, *, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        self._timeout = timeout

    def supports_cloning(self) -> bool:
        # 火山支持声音复刻，本期不实现，仅声明能力供前端置灰提示
        return True

    def _require_credential(self, credential: VoiceCredential) -> None:
        if not credential.configured:
            raise VoiceError(
                "VOICE_NO_CREDENTIAL",
                "请先配置 AppID 与 Access Token",
                status_code=400,
            )

    def _headers(self, credential: VoiceCredential) -> dict[str, str]:
        self._require_credential(credential)
        return {
            "Authorization": f"Bearer; {credential.token}",
            "Content-Type": "application/json",
        }

    def _app_block(self, credential: VoiceCredential, cluster: str) -> dict[str, str]:
        return {
            "appid": credential.app_id,
            "token": credential.token,
            "cluster": credential.cluster or cluster,
        }

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        self._require_credential(credential)
        return list(BUILTIN_VOICES)

    async def transcribe(
        self, credential: VoiceCredential, audio: bytes, content_type: str
    ) -> Transcript:
        """一句话识别：把整段音频一次传上去，拿回文字。"""
        headers = self._headers(credential)
        payload = {
            "app": self._app_block(credential, ASR_CLUSTER),
            "user": {"uid": credential.app_id},
            "audio": {
                "format": _audio_format(content_type),
                "data": base64.b64encode(audio).decode("ascii"),
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "sequence": 1,
                "nbest": 1,
            },
        }
        data = await self._post(f"{self._base}/api/v1/asr", headers, payload, "识别")
        text = _extract_asr_text(data)
        if not text:
            raise VoiceError("VOICE_ASR_EMPTY", "没有识别到内容，请再说一次")
        return Transcript(text=text, duration_ms=_extract_duration(data))

    async def synthesize(
        self,
        credential: VoiceCredential,
        text: str,
        voice_id: str,
        params: dict[str, object] | None = None,
    ) -> Speech:
        headers = self._headers(credential)
        audio_params: dict[str, Any] = {"voice_type": voice_id, "encoding": "mp3"}
        for source, target in (
            ("speed", "speed_ratio"),
            ("volume", "volume_ratio"),
            ("pitch", "pitch_ratio"),
        ):
            value = (params or {}).get(source)
            if value is None:
                continue
            try:
                ratio = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if ratio > 0:
                audio_params[target] = round(ratio, 2)
        payload = {
            "app": self._app_block(credential, TTS_CLUSTER),
            "user": {"uid": credential.app_id},
            "audio": audio_params,
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "operation": "query",
            },
        }
        data = await self._post(f"{self._base}/api/v1/tts", headers, payload, "合成")
        audio_b64 = data.get("data")
        if not isinstance(audio_b64, str) or not audio_b64:
            raise VoiceError("VOICE_TTS_EMPTY", "合成没有返回音频")
        try:
            raw = base64.b64decode(audio_b64)
        except (ValueError, TypeError) as exc:
            raise VoiceError("VOICE_TTS_BAD_RESPONSE", "合成返回的音频不是合法 base64") from exc
        return Speech(audio=raw, content_type="audio/mpeg")

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        self._require_credential(credential)
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
                response = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise VoiceError("VOICE_UNREACHABLE", f"{action}服务无法连接：{exc}") from exc
        if response.status_code in (401, 403):
            raise VoiceError("VOICE_AUTH_ERROR", "AppID 或 Token 无效", status_code=400)
        if response.status_code == 429:
            raise VoiceError("VOICE_RATE_LIMITED", "触发限流，请稍后再试", status_code=429)
        if response.status_code >= 400:
            raise VoiceError(
                "VOICE_UPSTREAM_ERROR",
                f"{action}失败（{response.status_code}）：{response.text[:160]}",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise VoiceError("VOICE_BAD_RESPONSE", f"{action}返回的不是 JSON") from exc
        if not isinstance(data, dict):
            raise VoiceError("VOICE_BAD_RESPONSE", f"{action}返回格式异常")
        # 火山在 HTTP 200 里也可能给业务错误码
        code = data.get("code")
        if isinstance(code, int) and code not in (0, 3000):
            message = str(data.get("message") or "")
            if 3001 <= code <= 3009 or code in (1001, 1002):
                raise VoiceError("VOICE_AUTH_ERROR", f"鉴权失败：{message}", status_code=400)
            raise VoiceError("VOICE_UPSTREAM_ERROR", f"{action}失败（{code}）：{message}")
        return data


def _audio_format(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "wav" in lowered:
        return "wav"
    if "mp3" in lowered or "mpeg" in lowered:
        return "mp3"
    return "ogg"


def _extract_asr_text(data: dict[str, Any]) -> str:
    result = data.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        utterances = result.get("utterances")
        if isinstance(utterances, list):
            parts = [
                str(item.get("text", "")).strip() for item in utterances if isinstance(item, dict)
            ]
            joined = "".join(part for part in parts if part)
            if joined:
                return joined
    raw_text = data.get("text")
    if isinstance(raw_text, str):
        return raw_text.strip()
    return ""


def _extract_duration(data: dict[str, Any]) -> int:
    audio_info = data.get("audio_info")
    if isinstance(audio_info, dict):
        duration = audio_info.get("duration")
        if isinstance(duration, (int, float)):
            return int(duration)
    return 0
