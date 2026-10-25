"""SSRF 防护：用户可填模型地址，必须挡住内网探测与云元数据接口。

策略：
1. 只允许 http/https，公网地址必须 https；
2. 禁止 URL 里带用户名密码、query、fragment；
3. 字面量 IP 直接判定；内网/回环/链路本地/保留段默认拒绝，只有
   allow_private=True（单机自用模式）才放行 localhost 与私有网段；
4. 拒绝歧义数字写法（2130706433、0x7f.0.0.1、127.1），它们会被系统解析成内网地址；
5. 域名做基本合法性校验，防止明显畸形输入。
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from app.core.errors import InvalidInput

_HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)
_BLOCKED_NETS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # 云元数据 / 链路本地
    ipaddress.ip_network("100.64.0.0/10"),  # 运营商级 NAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),  # 组播
    ipaddress.ip_network("240.0.0.0/4"),  # 保留
)


def _is_ambiguous_numeric(host: str) -> bool:
    lowered = host.lower()
    if "0x" in lowered:
        return True
    labels = host.split(".")
    return all(label.isdigit() for label in labels)


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> None:
    if any(ip in network for network in _BLOCKED_NETS if network.version == ip.version):
        raise InvalidInput("不允许访问该地址（保留/元数据地址）", code="MODEL_ENDPOINT_REJECTED")
    if ip.is_loopback:
        if not allow_private:
            raise InvalidInput(
                "本地地址需要开启「允许访问私有网段」后才能使用", code="MODEL_ENDPOINT_REJECTED"
            )
        return
    if ip.is_private:
        if not allow_private:
            raise InvalidInput(
                "私有网段地址需要开启「允许访问私有网段」后才能使用", code="MODEL_ENDPOINT_REJECTED"
            )
        return
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise InvalidInput("地址不可用", code="MODEL_ENDPOINT_REJECTED")


def validate_endpoint(url: str, *, allow_private: bool = False) -> str:
    """校验并规范化模型接入点地址；非法时抛 InvalidInput。"""
    raw = (url or "").strip()
    if not raw:
        raise InvalidInput("模型地址不能为空", code="MODEL_ENDPOINT_REJECTED")
    if len(raw) > 500:
        raise InvalidInput("模型地址过长", code="MODEL_ENDPOINT_REJECTED")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise InvalidInput("只支持 http/https 地址", code="MODEL_ENDPOINT_REJECTED")
    if parts.username or parts.password:
        raise InvalidInput("地址里不允许携带用户名密码", code="MODEL_ENDPOINT_REJECTED")
    if parts.query or parts.fragment:
        raise InvalidInput("模型地址不能带查询参数", code="MODEL_ENDPOINT_REJECTED")
    host = parts.hostname
    if not host:
        raise InvalidInput("模型地址缺少主机名", code="MODEL_ENDPOINT_REJECTED")
    if host.endswith("."):
        host = host[:-1]
    if len(host) > 253:
        raise InvalidInput("主机名过长", code="MODEL_ENDPOINT_REJECTED")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
        if _is_ambiguous_numeric(host):
            raise InvalidInput(
                "地址写法有歧义，请填写标准域名或 IP", code="MODEL_ENDPOINT_REJECTED"
            ) from None
        if not _HOST_RE.match(host):
            raise InvalidInput("主机名格式不合法", code="MODEL_ENDPOINT_REJECTED") from None
        if parts.scheme == "http" and not allow_private:
            raise InvalidInput(
                "公网模型地址必须使用 https", code="MODEL_ENDPOINT_REJECTED"
            ) from None
    else:
        _check_ip(ip, allow_private)
        if parts.scheme == "http":
            if not allow_private:
                raise InvalidInput("公网模型地址必须使用 https", code="MODEL_ENDPOINT_REJECTED")
            if not (ip.is_loopback or ip.is_private):
                raise InvalidInput("http 只允许用于本地/内网地址", code="MODEL_ENDPOINT_REJECTED")

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))
