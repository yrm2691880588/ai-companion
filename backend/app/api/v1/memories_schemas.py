"""记忆接口的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MemoryOut(BaseModel):
    id: int
    type: str
    type_label: str
    content: str
    confidence: float
    source_session_id: int | None = None
    quote: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class MemorySettingsIn(BaseModel):
    enabled: bool


class MemorySettingsOut(BaseModel):
    companion_id: int
    enabled: bool
