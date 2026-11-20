"""SSRF-safe URL validation used before Anysearch extraction."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit


class UnsafeUrlError(ValueError):
    """Raised when a URL is not a public HTTP(S) target."""


Resolver = Callable[..., Awaitable[list[tuple[Any, ...]]]]
RedirectRequest = Callable[[str], Awaitable[tuple[int, dict[str, str]]]]

_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
)
_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "instance-data",
}


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return bool(address.is_global)


def _parse_http_url(url: str) -> SplitResult:
    if not isinstance(url, str):
        raise UnsafeUrlError("URL 必须是字符串。")
    text = url.strip()
    if not text or len(text) > 4096:
        raise UnsafeUrlError("URL 为空或过长。")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise UnsafeUrlError("URL 包含控制字符。")
    if "\\" in text:
        raise UnsafeUrlError("URL 不允许反斜杠。")

    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("只允许公开的 http(s) URL。")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL 不允许包含用户名或密码。")
    try:
        parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL 端口无效。") from exc

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL 缺少主机名。")
    if "%" in hostname:
        raise UnsafeUrlError("URL 主机名不允许区域标识或百分号编码。")

    host = hostname.rstrip(".").lower()
    if not host or len(host) > 253:
        raise UnsafeUrlError("URL 主机名无效。")
    if host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise UnsafeUrlError("URL 指向本地或内部主机。")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UnsafeUrlError("URL 指向非公网地址。")

    normalized_host = f"[{host}]" if ":" in host else host
    netloc = normalized_host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return SplitResult(
        parsed.scheme.lower(),
        netloc,
        parsed.path or "/",
        parsed.query,
        parsed.fragment,
    )


async def _default_resolver(
    host: str,
    port: int,
    *,
    type: socket.SocketKind = socket.SOCK_STREAM,
) -> list[tuple[Any, ...]]:
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=type,
        proto=socket.IPPROTO_TCP,
    )


async def validate_public_http_url(
    url: str,
    *,
    resolver: Resolver | None = None,
) -> str:
    """Return a normalized URL only when its host resolves only to public IPs."""

    parsed = _parse_http_url(url)
    host = parsed.hostname or ""
    try:
        ipaddress.ip_address(host)
        return urlunsplit(parsed)
    except ValueError:
        pass

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve = resolver or _default_resolver
    try:
        results = await resolve(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise UnsafeUrlError("URL 主机无法解析。") from exc
    except asyncio.TimeoutError as exc:
        raise UnsafeUrlError("URL 主机解析超时。") from exc

    addresses: set[str] = set()
    for result in results or []:
        if len(result) < 5:
            continue
        sockaddr = result[4]
        if isinstance(sockaddr, tuple) and sockaddr:
            addresses.add(str(sockaddr[0]).split("%", 1)[0])
    if not addresses:
        raise UnsafeUrlError("URL 主机没有可用的公网地址。")
    if any(not _is_public_ip(address) for address in addresses):
        raise UnsafeUrlError("URL 主机解析到非公网地址。")
    return urlunsplit(parsed)


def redirect_target(current_url: str, location: str) -> str:
    """Resolve one redirect location without trusting a different scheme."""

    location = (location or "").strip()
    if not location:
        raise UnsafeUrlError("重定向缺少 Location。")
    target = urljoin(current_url, location)
    if urlsplit(current_url).scheme.lower() == "https" and urlsplit(target).scheme.lower() == "http":
        raise UnsafeUrlError("不允许从 HTTPS 降级重定向到 HTTP。")
    return target


async def resolve_safe_redirects(
    start_url: str,
    request: RedirectRequest,
    *,
    max_redirects: int = 3,
    resolver: Resolver | None = None,
) -> str:
    """Follow redirects manually, validating every hop before requesting it."""

    if max_redirects < 0 or max_redirects > 10:
        raise ValueError("max_redirects 必须在 0 到 10 之间。")
    current = start_url
    seen: set[str] = set()
    for hop in range(max_redirects + 1):
        current = await validate_public_http_url(current, resolver=resolver)
        if current in seen:
            raise UnsafeUrlError("重定向出现循环。")
        seen.add(current)
        status, headers = await request(current)
        if not 300 <= status < 400:
            return current
        if hop >= max_redirects:
            raise UnsafeUrlError("重定向次数超过上限。")
        location = headers.get("Location") or headers.get("location") or ""
        current = redirect_target(current, location)
    raise UnsafeUrlError("重定向次数超过上限。")

class PublicResolver:
    """Aiohttp resolver that rejects any private address at connect time."""

    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = resolver

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        if self._resolver is not None:
            results = await self._resolver(host, port, type=socket.SOCK_STREAM)
        else:
            loop = asyncio.get_running_loop()
            results = await loop.getaddrinfo(
                host,
                port,
                family=family,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )

        resolved: list[dict[str, Any]] = []
        for item in results or []:
            if len(item) < 5:
                continue
            result_family = int(item[0])
            if family not in (socket.AF_UNSPEC, result_family):
                continue
            sockaddr = item[4]
            if not isinstance(sockaddr, tuple) or not sockaddr:
                continue
            address = str(sockaddr[0]).split("%", 1)[0]
            if not _is_public_ip(address):
                raise OSError("DNS resolved to a non-public address")
            resolved.append(
                {
                    "hostname": host,
                    "host": address,
                    "port": int(sockaddr[1]) if len(sockaddr) > 1 else port,
                    "family": result_family,
                    "proto": int(item[2]),
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not resolved:
            raise OSError("DNS returned no usable public address")
        return resolved

    async def close(self) -> None:
        return None