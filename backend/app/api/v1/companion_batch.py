"""批量删除伴侣：一次确认删除多个，逐个记录结果。

本层只做协议映射：请求转参数、调用领域层、把结果转成响应模型。
确认词、数量上限、去重等业务规则在 `app.domain.companions`。

安全设计：
- 必须显式传入要删的 id 列表，不做「全选删除」的服务端隐式展开；
- 必须输入确认词（由领域层校验）；
- 上限由领域层限制，避免一次误删整库；
- 逐个删除并返回每个的成功/失败原因，部分失败不影响其它；
- 删除走软删 + 排队硬清，与单个删除路径一致。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_companion_service, get_current_user_id, get_deletion_service
from app.core.errors import AppError
from app.domain.companions import (
    BATCH_DELETE_CONFIRM,
    MAX_BATCH_DELETE,
    CompanionService,
)
from app.domain.deletion import DeletionService

router = APIRouter(prefix="/v1/companions", tags=["companions"])

_LOG = logging.getLogger(__name__)


class BatchDeleteRules(BaseModel):
    """批量删除的前端提示规则：确认词与上限由后端给出，避免两处硬编码。"""

    confirm: str
    max_batch: int


@router.get("/batch-delete/rules", response_model=BatchDeleteRules)
async def batch_delete_rules(
    _user: Annotated[str, Depends(get_current_user_id)],
) -> BatchDeleteRules:
    """返回确认词与数量上限，供前端展示，避免前端复制业务常量。"""
    return BatchDeleteRules(confirm=BATCH_DELETE_CONFIRM, max_batch=MAX_BATCH_DELETE)


class BatchDeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=MAX_BATCH_DELETE)
    confirm: str = Field(min_length=1, max_length=20)


class BatchDeleteFailure(BaseModel):
    """单个伴侣删除失败的原因。"""

    id: int
    reason: str


class BatchDeleteOut(BaseModel):
    deleted: list[int] = Field(default_factory=list)
    failed: list[BatchDeleteFailure] = Field(default_factory=list)


@router.post("/batch-delete", response_model=BatchDeleteOut)
async def batch_delete(
    payload: BatchDeleteIn,
    background: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
    deletion: Annotated[DeletionService, Depends(get_deletion_service)],
) -> BatchDeleteOut:
    """批量删除伴侣；逐个执行，返回成功与失败明细。"""
    # 业务校验（确认词、数量上限、去重）由 domain 层负责
    ids = service.check_batch_delete(payload.ids, payload.confirm)
    result = BatchDeleteOut()

    for companion_id in ids:
        try:
            # 用确认词走批量专用路径；不拿 record.name 自我确认
            await service.delete_for_batch(user_id, companion_id, payload.confirm)
            job = await deletion.enqueue(user_id, companion_id)
            background.add_task(deletion.run_job, job.id)
            result.deleted.append(companion_id)
        except AppError as exc:
            # 业务错误（不存在、校验失败）：原样回给用户，他需要知道原因
            result.failed.append(BatchDeleteFailure(id=companion_id, reason=exc.message))
        except Exception as exc:  # noqa: BLE001 - 单个失败不能中断整批
            # 非预期错误：记录完整堆栈到日志，对外只给不暴露内部细节的说明
            _LOG.error("批量删除失败 id=%s", companion_id, exc_info=exc)
            result.failed.append(
                BatchDeleteFailure(id=companion_id, reason="删除时出现内部错误，详见日志")
            )

    return result
