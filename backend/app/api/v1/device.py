"""设备与运行环境诊断：只读，用于排查跨端来源。

不返回任何密钥或个人数据，只回当前请求被识别成哪台设备。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.device import current_device_id

router = APIRouter(prefix="/v1/device", tags=["device"])


@router.get("/whoami")
async def whoami() -> dict[str, str]:
    """当前请求的设备标识；未带 X-Device-Id 时回退为 local。"""
    return {"device_id": current_device_id()}
