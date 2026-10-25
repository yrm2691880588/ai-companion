"""官方模板接口：列表、详情（从模板创建在伴侣接口里）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_template_repo
from app.api.v1.companion_schemas import TemplateOut
from app.core.errors import AppError
from app.domain.templates import TemplateRepository

router = APIRouter(prefix="/v1/templates", tags=["templates"])


def _out(template: object) -> TemplateOut:
    return TemplateOut(
        key=template.key,  # type: ignore[attr-defined]
        category=template.category,  # type: ignore[attr-defined]
        name=template.name,  # type: ignore[attr-defined]
        tagline=template.tagline,  # type: ignore[attr-defined]
        persona=template.persona,  # type: ignore[attr-defined]
    )


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    repo: Annotated[TemplateRepository, Depends(get_template_repo)],
    category: Annotated[str | None, Query(max_length=32)] = None,
) -> list[TemplateOut]:
    return [_out(item) for item in await repo.list(category)]


@router.get("/{template_key}", response_model=TemplateOut)
async def get_template(
    template_key: str,
    repo: Annotated[TemplateRepository, Depends(get_template_repo)],
) -> TemplateOut:
    template = await repo.get(template_key)
    if template is None:
        raise AppError(code="TEMPLATE_NOT_FOUND", message="模板不存在", status_code=404)
    return _out(template)
