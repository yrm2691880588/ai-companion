"""语音供应商注册表：按 key 取适配器。"""

from __future__ import annotations

from app.infra.voice.base import VoiceProvider
from app.infra.voice.volcengine import VolcengineVoiceProvider


class VoiceProviderRegistry:
    def __init__(
        self,
        providers: dict[str, VoiceProvider] | None = None,
        *,
        tts_resource_id: str = "",
        asr_resource_id: str = "",
    ) -> None:
        self._providers: dict[str, VoiceProvider] = providers or {
            "volcengine": VolcengineVoiceProvider(
                tts_resource_id=tts_resource_id or "seed-tts-2.0",
                asr_resource_id=asr_resource_id or "volc.seedasr.auc",
            )
        }

    @property
    def keys(self) -> list[str]:
        return list(self._providers)

    def get(self, key: str) -> VoiceProvider:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise KeyError(f"未注册的语音供应商：{key}") from exc

    def describe(self) -> list[dict[str, object]]:
        return [
            {
                "key": provider.key,
                "display_name": provider.display_name,
                "supports_cloning": provider.supports_cloning(),
            }
            for provider in self._providers.values()
        ]
