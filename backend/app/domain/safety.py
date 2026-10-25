"""安全：危机信号识别、提示词增强与事件留痕。

V1 只做「识别 + 提示模型 + 留痕」，不做强制中断：
强行切换成机器口吻会破坏信任，正确做法是让角色先接住情绪，再给现实资源。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

CRISIS_KEYWORDS = (
    "不想活",
    "活不下去",
    "活着没意思",
    "自杀",
    "自残",
    "轻生",
    "结束生命",
    "想死",
    "割腕",
    "跳楼",
)

CRISIS_NOTE = """
# 紧急安全提示（最高优先级）
用户刚才的话里可能包含自伤/轻生信号。请：
1. 先用这个角色自己的方式认真接住情绪，不要评判、不要说教、不要立刻转移话题；
2. 明确告诉用户「你现在的感受很重要」，并给出现实求助渠道：
   - 全国 24 小时心理援助热线：12356
   - 紧急情况请拨打 120 或前往最近的医院急诊
3. 不要承诺保密，不要独自处理危机；如果用户有立即危险，建议马上联系身边可信任的人。
4. 保持角色语气，但这条安全要求高于人设。
"""

RESTRICTED_KEYWORDS = (
    "炸弹",
    "制毒",
    "毒品制作",
    "儿童色情",
    "洗钱",
    "诈骗教程",
    "黑客教程",
)

RESTRICTED_NOTE = """
# 边界要求
用户可能在做违法或危险的具体询问。请：
1. 用这个角色的口吻，简短说明这件事不能帮，不评判用户本人；
2. 不提供任何具体方法、步骤、材料或规避手段；
3. 如果用户有现实风险，建议联系专业机构或身边可信任的人。
"""


@dataclass(frozen=True, slots=True)
class SafetyAssessment:
    level: str  # normal | crisis | restricted
    keywords: list[str]

    @property
    def is_crisis(self) -> bool:
        return self.level == "crisis"

    @property
    def is_restricted(self) -> bool:
        return self.level == "restricted"


def assess_input(text: str) -> SafetyAssessment:
    content = text or ""
    crisis_hits = [keyword for keyword in CRISIS_KEYWORDS if keyword in content]
    if crisis_hits:
        return SafetyAssessment(level="crisis", keywords=crisis_hits)
    restricted_hits = [keyword for keyword in RESTRICTED_KEYWORDS if keyword in content]
    if restricted_hits:
        return SafetyAssessment(level="restricted", keywords=restricted_hits)
    return SafetyAssessment(level="normal", keywords=[])


class SafetyEventRepository(Protocol):
    async def record(
        self, user_id: str, session_id: int | None, level: str, keywords: list[str]
    ) -> None: ...


class InMemorySafetyRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def record(
        self, user_id: str, session_id: int | None, level: str, keywords: list[str]
    ) -> None:
        self.events.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "level": level,
                "keywords": list(keywords),
                "created_at": datetime.now(UTC),
            }
        )
