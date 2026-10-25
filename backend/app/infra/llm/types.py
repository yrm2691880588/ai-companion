"""模型层的公共类型：任务、消息、流式分片、模型规格与统一错误。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.infra.llm.pricing import BandedPrice


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


class TaskName(StrEnum):
    """按用途区分的模型任务位，路由器据此选择模型。"""

    CHAT_MAIN = "chat_main"
    PERSONA_GENERATE = "persona_generate"
    MEMORY_EXTRACT = "memory_extract"
    SUMMARIZE = "summarize"
    SAFETY_CHECK = "safety_check"
    ROLEPLAY_REVIEW = "roleplay_review"
    TITLE_GENERATE = "title_generate"


class Capability(StrEnum):
    STREAM = "stream"
    JSON = "json"
    TOOLS = "tools"
    THINKING = "thinking"
    VISION = "vision"


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens or (self.cache_hit_tokens + self.cache_miss_tokens)

    @property
    def hit_ratio(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        if total <= 0:
            return 0.0
        return self.cache_hit_tokens / total


@dataclass(slots=True)
class ChatChunk:
    delta: str = ""
    finish_reason: str | None = None
    usage: Usage | None = None
    model_key: str | None = None
    provider_key: str | None = None


@dataclass(frozen=True, slots=True)
class ChatParams:
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    thinking: bool = False
    json_mode: bool = False
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """一个可调用的模型档案（对应 model_profiles 一行）。"""

    key: str  # provider_key:model_name，全局唯一
    provider_key: str
    model_name: str
    display_name: str
    context_window: int
    max_output: int
    supports: frozenset[Capability]
    price: BandedPrice
    embedding_dim: int | None = None
    aliases: tuple[str, ...] = ()
    notes: str = ""

    def supports_all(self, required: frozenset[Capability]) -> bool:
        return required <= self.supports

    @property
    def input_price_is_zero(self) -> bool:
        return self.price.peak.input_miss == 0 and self.price.peak.output == 0


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """一个接入点（对应 model_providers 一行）。api_key 仅在运行时存在。"""

    key: str
    name: str
    kind: str  # openai | anthropic
    base_url: str
    api_key: str = field(default="", repr=False)
    allow_private: bool = False
    timeout_seconds: float = 60.0
    thinking_style: str = "none"  # deepseek | none：思考模式的厂商专属开关写法


class LLMError(Exception):
    """模型调用错误的统一基类。"""

    code = "LLM_ERROR"
    retryable = False

    def __init__(self, message: str = "", *, status: int | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.status = status


class RateLimited(LLMError):
    code = "RATE_LIMITED"
    retryable = True


class ContextOverflow(LLMError):
    code = "CONTEXT_OVERFLOW"
    retryable = True


class AuthError(LLMError):
    code = "AUTH_ERROR"


class UpstreamError(LLMError):
    code = "UPSTREAM_ERROR"
    retryable = True


class LLMTimeout(LLMError):
    code = "LLM_TIMEOUT"
    retryable = True


class ContentBlocked(LLMError):
    """上游内容审核拦截：不允许降级重试（否则等于绕过审核）。"""

    code = "CONTENT_BLOCKED"


class MalformedStream(LLMError):
    code = "MALFORMED_STREAM"
    retryable = True


class StreamAborted(LLMError):
    """首个 token 已下发后断流：不允许整段重试，只能续写或重新生成。"""

    code = "STREAM_ABORTED"


class AllProvidersFailed(LLMError):
    """整条路由链都失败，附带每次失败的原因。"""

    code = "ALL_PROVIDERS_FAILED"

    def __init__(self, attempts: list[tuple[str, str]]) -> None:
        self.attempts = attempts
        summary = "；".join(f"{model}: {reason}" for model, reason in attempts) or "无可用模型"
        super().__init__(f"所有模型均不可用（{summary}）")
