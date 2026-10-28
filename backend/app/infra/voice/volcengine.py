"""火山引擎语音适配（豆包语音，新版控制台 API Key 接入）。

实测确认（2026-10-28，新版控制台账号）：
- 合成：POST /api/v3/tts/unidirectional，资源 ID `seed-tts-2.0`
  旧版 `volc.service_type.10029` 与 `/api/v1/tts` 在新版账号下会报
  `requested resource not granted`，不要再用。
- 识别：录音文件识别两步流程
  POST /api/v3/auc/bigmodel/submit  提交
  POST /api/v3/auc/bigmodel/query   轮询结果
  资源 ID `volc.seedasr.auc`
- 鉴权头：X-Api-App-Id / X-Api-Access-Key / X-Api-Resource-Id
  （不是旧版的 Authorization: Bearer; token）

资源 ID 做成可配置，因为不同账号/套餐可能不同。
"""

from __future__ import annotations

import asyncio
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
DEFAULT_TTS_RESOURCE = "seed-tts-2.0"
DEFAULT_ASR_RESOURCE = "volc.seedasr.auc"

# 新版控制台 2.0 音色（voice_type）。用户可在设置里改，或用 /voices 刷新
BUILTIN_VOICES = [
    VoiceOption("zh_female_vv_uranus_bigtts", "通用女声", "女", ["通用", "自然"]),
    VoiceOption("saturn_zh_female_keainvsheng_tob", "可爱女声", "女", ["可爱", "年轻"]),
    VoiceOption("saturn_zh_female_tiaopigongzhu_tob", "俏皮公主", "女", ["俏皮", "活泼"]),
    VoiceOption("zh_male_M392_conversation_wvae_bigtts", "通用男声", "男", ["通用", "沉稳"]),
    VoiceOption("zh_female_shuangkuaisisi_moon_bigtts", "爽快思思", "女", ["爽快", "干练"]),
]

# 识别状态码：成功 / 静音无语音 / 处理中
ASR_OK = 20000000
ASR_SILENCE = 20000003
ASR_PENDING = {20000001, 20000002}


class VolcengineVoiceProvider:
    key = "volcengine"
    display_name = "火山引擎（豆包语音）"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        tts_resource_id: str = DEFAULT_TTS_RESOURCE,
        asr_resource_id: str = DEFAULT_ASR_RESOURCE,
    ) -> None:
        self._base = (base_url or DEFAULT_BASE).rstrip("/")
        self._timeout = timeout
        self._tts_resource = tts_resource_id or DEFAULT_TTS_RESOURCE
        self._asr_resource = asr_resource_id or DEFAULT_ASR_RESOURCE

    def supports_cloning(self) -> bool:
        # 火山支持声音复刻，本期不实现，只声明能力供前端置灰提示
        return True

    # ---------- 鉴权 ----------

    def _require_credential(self, credential: VoiceCredential) -> None:
        if not credential.configured:
            raise VoiceError(
                "VOICE_NO_CREDENTIAL", "请先配置 AppID 与 Access Token", status_code=400
            )

    def _headers(
        self, credential: VoiceCredential, *, resource_id: str, request_id: str | None = None
    ) -> dict[str, str]:
        self._require_credential(credential)
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Id": credential.app_id,
            "X-Api-Access-Key": credential.token,
            "X-Api-Resource-Id": resource_id,
        }
        if request_id:
            headers["X-Api-Request-Id"] = request_id
        return headers

    # ---------- 音色 ----------

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        self._require_credential(credential)
        return list(BUILTIN_VOICES)

    # ---------- 合成 ----------

    async def synthesize(
        self,
        credential: VoiceCredential,
        text: str,
        voice_id: str,
        params: dict[str, object] | None = None,
    ) -> Speech:
        """单向流式合成：接口返回若干 JSON 块，每块的 data 是一段 base64 音频。"""
        headers = self._headers(credential, resource_id=self._tts_resource)
        audio_params: dict[str, Any] = {"format": "mp3", "sample_rate": 24000}
        # 2.0 参数：语速/音量在 [0.5, 2.0]，超出会被拒绝
        for source, target in (("speed", "speech_rate"), ("volume", "loudness_rate")):
            value = (params or {}).get(source)
            if value is None:
                continue
            try:
                ratio = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if ratio > 0:
                # 服务端用「相对 1.0 的百分比偏移」，例如 1.2 倍 => 20
                audio_params[target] = int(round((ratio - 1.0) * 100))

        payload = {
            "user": {"uid": credential.app_id},
            "req_params": {
                "text": text,
                "speaker": voice_id,
                "audio_params": audio_params,
            },
        }

        chunks: list[bytes] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self._base}/api/v3/tts/unidirectional",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code in (401, 403):
                        await response.aread()
                        raise VoiceError(
                            "VOICE_AUTH_ERROR", "AppID 或 Access Key 无效", status_code=400
                        )
                    if response.status_code >= 400:
                        await response.aread()
                        raise VoiceError(
                            "VOICE_TTS_ERROR",
                            f"合成失败（{response.status_code}）：{response.reason_phrase}",
                        )
                    buffer = ""
                    async for raw in response.aiter_text():
                        buffer += raw
                        # 服务端按行返回多个 JSON 对象
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            self._collect_tts_chunk(line, chunks)
                    if buffer.strip():
                        self._collect_tts_chunk(buffer, chunks)
            except httpx.HTTPError as exc:
                raise VoiceError("VOICE_UNREACHABLE", f"合成服务无法连接：{exc}") from exc

        if not chunks:
            raise VoiceError("VOICE_TTS_EMPTY", "合成没有返回音频")
        return Speech(audio=b"".join(chunks), content_type="audio/mpeg")

    @staticmethod
    def _collect_tts_chunk(line: str, chunks: list[bytes]) -> None:
        text = line.strip()
        if not text:
            return
        try:
            data = json.loads(text)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        code = data.get("code")
        if isinstance(code, int) and code not in (0, 20000000):
            message = str(data.get("message") or "")
            if "resource not granted" in message:
                raise VoiceError(
                    "VOICE_RESOURCE_NOT_GRANTED",
                    "该应用未开通语音合成资源，请在火山控制台勾选「豆包语音合成模型 2.0」",
                    status_code=400,
                )
            if code:
                raise VoiceError("VOICE_TTS_ERROR", f"合成失败（{code}）：{message}")
        audio_b64 = data.get("data")
        if isinstance(audio_b64, str) and audio_b64:
            try:
                chunks.append(base64.b64decode(audio_b64))
            except (ValueError, TypeError):
                return

    # ---------- 识别（提交 + 轮询）----------

    async def transcribe(
        self, credential: VoiceCredential, audio: bytes, content_type: str
    ) -> Transcript:
        """录音文件识别：先提交任务，再按 request-id 轮询结果。"""
        request_id = str(uuid.uuid4())
        payload = {
            "user": {"uid": credential.app_id},
            "audio": {
                "format": _audio_format(content_type),
                "data": base64.b64encode(audio).decode("ascii"),
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "show_utterances": True,
            },
        }
        headers = self._headers(credential, resource_id=self._asr_resource, request_id=request_id)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            submit_status, submit_message = await self._asr_submit(client, headers, payload)
            if submit_status == ASR_SILENCE:
                raise VoiceError("VOICE_ASR_EMPTY", "没有识别到内容，请再说一次")
            # 提交返回「处理中」属正常，继续轮询；只有真正失败才抛
            if submit_status != ASR_OK and submit_status not in ASR_PENDING:
                raise _asr_error(submit_status, submit_message)

            data = await self._asr_poll(client, headers)

        text = _extract_asr_text(data)
        if not text:
            raise VoiceError("VOICE_ASR_EMPTY", "没有识别到内容，请再说一次")
        return Transcript(text=text, duration_ms=_extract_duration(data))

    async def _asr_submit(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> tuple[int, str]:
        try:
            response = await client.post(
                f"{self._base}/api/v3/auc/bigmodel/submit",
                headers={**headers, "X-Api-Sequence": "-1"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise VoiceError("VOICE_UNREACHABLE", f"识别服务无法连接：{exc}") from exc
        return _asr_status(response)

    async def _asr_poll(
        self, client: httpx.AsyncClient, headers: dict[str, str], *, attempts: int = 20
    ) -> dict[str, Any]:
        """轮询结果；最多等约 10 秒（0.5 秒一次），超时按失败处理。"""
        for _ in range(attempts):
            await asyncio.sleep(0.5)
            try:
                response = await client.post(
                    f"{self._base}/api/v3/auc/bigmodel/query", headers=headers, json={}
                )
            except httpx.HTTPError as exc:
                raise VoiceError("VOICE_UNREACHABLE", f"识别结果查询失败：{exc}") from exc
            status, message = _asr_status(response)
            if status in ASR_PENDING:
                continue
            if status == ASR_SILENCE:
                raise VoiceError("VOICE_ASR_EMPTY", "没有识别到内容，请再说一次")
            if status != ASR_OK:
                raise _asr_error(status, message)
            try:
                return response.json()
            except ValueError as exc:
                raise VoiceError("VOICE_BAD_RESPONSE", "识别结果不是合法 JSON") from exc
        raise VoiceError("VOICE_ASR_TIMEOUT", "识别超时，请再说一次")

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        """真探活：合成一小段，确认资源已开通且音色可用。"""
        voices = await self.list_voices(credential)
        await self.synthesize(credential, "你好", voices[0].voice_id)
        return {"ok": True, "voice_count": len(voices)}


# ---------- 工具函数 ----------


def _asr_status(response: httpx.Response) -> tuple[int, str]:
    raw = response.headers.get("X-Api-Status-Code", "")
    message = response.headers.get("X-Api-Message", "")
    try:
        return int(raw), message
    except (TypeError, ValueError):
        return response.status_code, message


def _asr_error(status: int, message: str) -> VoiceError:
    if "resource not granted" in message:
        return VoiceError(
            "VOICE_RESOURCE_NOT_GRANTED",
            "该应用未开通语音识别资源，请在火山控制台勾选「录音文件识别模型 2.0」",
            status_code=400,
        )
    return VoiceError("VOICE_ASR_ERROR", f"识别失败（{status}）：{message}")


def _audio_format(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "wav" in lowered:
        return "wav"
    if "mp3" in lowered or "mpeg" in lowered:
        return "mp3"
    if "ogg" in lowered or "webm" in lowered:
        return "ogg"
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
