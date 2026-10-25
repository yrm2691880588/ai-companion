"""会话与消息的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateIn(BaseModel):
    title: str = Field(default="", max_length=60)


class SessionOut(BaseModel):
    id: int
    companion_id: int
    title: str
    state: str
    created_at: datetime
    last_message_at: datetime | None = None


class MessageOut(BaseModel):
    id: int
    session_id: int
    seq: int
    role: str
    content: str
    created_at: datetime


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    client_request_id: str | None = Field(default=None, max_length=64)


class SummaryOut(BaseModel):
    session_id: int
    summary: str | None = None
    covered_seq: int = 0
    updated_at: datetime | None = None
