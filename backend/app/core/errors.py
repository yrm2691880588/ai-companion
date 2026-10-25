"""统一错误模型：HTTP 层与 LLM 层共用一套错误码。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppError(Exception):
    """业务错误的基类。code 用于前端识别与文案映射。"""

    code: str
    message: str
    status_code: int = 400
    details: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - 仅日志用
        return f"{self.code}: {self.message}"


class NotFound(AppError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class Forbidden(AppError):
    def __init__(self, message: str = "无权访问") -> None:
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


class InvalidInput(AppError):
    def __init__(self, message: str, code: str = "INVALID_INPUT") -> None:
        super().__init__(code=code, message=message, status_code=422)
