"""演练接口的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScenarioOut(BaseModel):
    key: str
    title: str
    category: str
    role: str
    goal: str
    difficulty: int
    max_turns: int
    opening: str
    tips: str = ""


class RunStartIn(BaseModel):
    scenario_key: str = Field(min_length=1, max_length=64)
    max_turns: int | None = Field(default=None, ge=1, le=20)


class RunOut(BaseModel):
    id: int
    companion_id: int
    scenario_key: str
    session_id: int
    status: str
    max_turns: int
    turns_played: int
    review: dict[str, Any] | None = None
    created_at: datetime
    finished_at: datetime | None = None


class RunStartOut(RunOut):
    scenario: ScenarioOut
    opening: str


class TurnIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
