"""Bounded Anysearch MCP client adapted for the Zhiban module host."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from .security import (
    PublicResolver,
    UnsafeUrlError,
    resolve_safe_redirects,
    validate_public_http_url,
)


class AnySearchError(RuntimeError):
    """Raised when Anysearch is not configured or a bounded request fails."""

    def __init__(self, message: str, *, code: str = "request_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _CacheEntry:
    value: str
    expires_at: float
    size: int


class TTLCache:
    """Small in-memory LRU cache with entry, byte, and TTL limits."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 120,
        max_entries: int = 64,
        max_bytes: int = 2 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
        self.max_bytes = max(0, int(max_bytes))
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._bytes = 0

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._discard(key)

    def _discard(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._bytes -= entry.size

    def get(self, key: str) -> str | None:
        now = self._clock()
        self._purge_expired(now)
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry.value

    def put(self, key: str, value: str) -> bool:
        if not isinstance(value, str) or self.ttl_seconds <= 0 or self.max_entries <= 0:
            return False
        size = len(value.encode("utf-8"))
        if size <= 0 or size > self.max_bytes:
            return False
        now = self._clock()
        self._purge_expired(now)
        self._discard(key)
        self._entries[key] = _CacheEntry(value, now + self.ttl_seconds, size)
        self._bytes += size
        while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
            oldest = next(iter(self._entries))
            self._discard(oldest)
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    @property
    def size_bytes(self) -> int:
        return self._bytes


class AnySearchClient:
    endpoint = "https://api.anysearch.com/mcp"

    def __init__(
        self,
        api_key: str = "",
        timeout: float = 20,
        *,
        max_response_bytes: int = 1024 * 1024,
        max_concurrency: int = 2,
        cache_ttl_seconds: int = 120,
        cache_max_entries: int = 64,
        cache_max_bytes: int = 2 * 1024 * 1024,
        max_query_chars: int = 2000,
        preflight_redirects: bool = True,
        max_redirects: int = 3,
        session_factory: Callable[[], Any] | None = None,
        resolver: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.timeout = max(1.0, min(float(timeout), 120.0))
        self.max_response_bytes = max(1024, min(int(max_response_bytes), 8 * 1024 * 1024))
        self.max_concurrency = max(1, min(int(max_concurrency), 8))
        self.max_query_chars = max(64, min(int(max_query_chars), 8000))
        self.preflight_redirects = bool(preflight_redirects)
        self.max_redirects = max(0, min(int(max_redirects), 10))
        self._session_factory = session_factory
        self._resolver = resolver
        self._session: Any | None = None
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._cache = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
            max_bytes=cache_max_bytes,
            clock=clock,
        )

    def __repr__(self) -> str:
        state = "configured" if self.api_key else "not-configured"
        return f"AnySearchClient(endpoint={self.endpoint!r}, api_key={state})"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def public_status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "endpoint": self.endpoint,
            "max_concurrency": self.max_concurrency,
            "max_response_bytes": self.max_response_bytes,
            "max_query_chars": self.max_query_chars,
            "cache_ttl_seconds": self._cache.ttl_seconds,
        }

    def _redact(self, text: Any, *, limit: int = 500) -> str:
        value = str(text)
        if self.api_key:
            value = value.replace(self.api_key, "[REDACTED]")
        value = re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s&,}\"']+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(authorization\s*[=:]\s*)[^\s,}\"']+", r"\1[REDACTED]", value)
        return value[:limit]

    def _require_key(self) -> None:
        if not self.api_key:
            raise AnySearchError("未配置 Anysearch API Key，联网搜索未启用。", code="not_configured")

    def _validate_query(self, query: Any) -> str:
        value = str(query or "").strip()
        if not value:
            raise AnySearchError("搜索关键词不能为空。", code="invalid_argument")
        if len(value) > self.max_query_chars:
            raise AnySearchError(
                f"搜索关键词超过 {self.max_query_chars} 字符上限。",
                code="invalid_argument",
            )
        return value

    async def _get_session(self) -> Any:
        if self._session is not None and not getattr(self._session, "closed", False):
            return self._session
        if self._session_factory is not None:
            self._session = self._session_factory()
        else:
            connector = aiohttp.TCPConnector(
                limit=self.max_concurrency,
                limit_per_host=self.max_concurrency,
                ttl_dns_cache=300,
                resolver=PublicResolver(self._resolver),
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                trust_env=False,
            )
        return self._session

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and not getattr(session, "closed", False):
            close = getattr(session, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result

    async def _read_limited(self, response: Any, limit: int) -> bytes:
        content_length = None
        headers = getattr(response, "headers", {}) or {}
        try:
            content_length = int(headers.get("Content-Length", headers.get("content-length", 0)) or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length and content_length > limit:
            raise AnySearchError("Anysearch 响应超过大小上限。", code="response_too_large")

        content = getattr(response, "content", None)
        if content is not None and hasattr(content, "iter_chunked"):
            chunks: list[bytes] = []
            total = 0
            async for chunk in content.iter_chunked(64 * 1024):
                total += len(chunk)
                if total > limit:
                    raise AnySearchError("Anysearch 响应超过大小上限。", code="response_too_large")
                chunks.append(chunk)
            return b"".join(chunks)

        read = getattr(response, "read", None)
        if read is None:
            raise AnySearchError("Anysearch 响应无法读取。", code="invalid_response")
        data = await read()
        if len(data) > limit:
            raise AnySearchError("Anysearch 响应超过大小上限。", code="response_too_large")
        return data

    def _cache_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return json.dumps(
            {"tool": tool_name, "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        self._require_key()
        cache_key = self._cache_key(tool_name, arguments)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        async with self._semaphore:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            session = await self._get_session()
            try:
                async with session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    status = int(getattr(response, "status", 0))
                    if 300 <= status < 400:
                        raise AnySearchError("Anysearch API 返回重定向，已拒绝。", code="redirect_rejected")
                    if status >= 400:
                        detail = await self._read_limited(response, min(self.max_response_bytes, 4096))
                        message = detail.decode("utf-8", errors="replace")
                        raise AnySearchError(
                            f"Anysearch HTTP {status}: {self._redact(message)}",
                            code="http_error",
                        )
                    body = await self._read_limited(response, self.max_response_bytes)
            except AnySearchError:
                raise
            except asyncio.TimeoutError as exc:
                raise AnySearchError("Anysearch 请求超时。", code="timeout") from exc
            except aiohttp.ClientError as exc:
                raise AnySearchError(
                    f"Anysearch 网络连接失败：{self._redact(exc)}",
                    code="network_error",
                ) from exc
            except OSError as exc:
                raise AnySearchError(
                    f"Anysearch 网络连接失败：{self._redact(exc)}",
                    code="network_error",
                ) from exc

        try:
            text = body.decode("utf-8", errors="replace")
        except Exception as exc:
            raise AnySearchError("Anysearch 响应编码无效。", code="invalid_response") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnySearchError("Anysearch 返回了无效 JSON。", code="invalid_response") from exc
        if not isinstance(data, dict):
            raise AnySearchError("Anysearch 返回格式无效。", code="invalid_response")
        if "error" in data:
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else error
            raise AnySearchError(
                f"Anysearch API 错误：{self._redact(message or error)}",
                code="api_error",
            )
        result = data.get("result", {})
        content = result.get("content", []) if isinstance(result, dict) else []
        output = ""
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    output = str(item.get("text", ""))
                    break
        if not output:
            output = json.dumps(result, ensure_ascii=False, indent=2)
        if len(output.encode("utf-8")) > self.max_response_bytes:
            raise AnySearchError("Anysearch 结果超过大小上限。", code="response_too_large")
        self._cache.put(cache_key, output)
        return output

    async def _probe_redirect(self, url: str) -> tuple[int, dict[str, str]]:
        async with self._semaphore:
            session = await self._get_session()
            async with session.get(
                url,
                allow_redirects=False,
                headers={"Range": "bytes=0-0", "User-Agent": "Zhiban-AnySearch/0.3"},
                timeout=aiohttp.ClientTimeout(total=min(self.timeout, 10)),
            ) as response:
                headers = {
                    str(key): str(value)
                    for key, value in (getattr(response, "headers", {}) or {}).items()
                }
                return int(getattr(response, "status", 0)), headers

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        freshness: str = "",
        content_types: list[str] | None = None,
    ) -> str:
        query = self._validate_query(query)
        arguments: dict[str, Any] = {"query": query}
        if max_results is not None:
            arguments["max_results"] = max_results
        if freshness:
            arguments["freshness"] = freshness
        if content_types:
            arguments["content_types"] = content_types
        return await self._call("search", arguments)

    async def vertical_search(
        self,
        query: str,
        *,
        domain: str,
        sub_domain: str,
        zone: str = "",
        max_results: int | None = None,
        freshness: str = "",
        content_types: list[str] | None = None,
        sub_domain_params: dict[str, Any] | None = None,
    ) -> str:
        query = self._validate_query(query)
        arguments: dict[str, Any] = {
            "query": query,
            "domain": domain,
            "sub_domain": sub_domain,
        }
        if zone:
            arguments["zone"] = zone
        if max_results is not None:
            arguments["max_results"] = max_results
        if freshness:
            arguments["freshness"] = freshness
        if content_types:
            arguments["content_types"] = content_types
        if sub_domain_params:
            arguments["sub_domain_params"] = sub_domain_params
        return await self._call("search", arguments)

    async def list_domains(self, *, domain: str = "", domains: list[str] | None = None) -> str:
        if domains:
            return await self._call("list_domains", {"domains": domains})
        return await self._call("list_domains", {"domain": domain})

    async def batch_search(self, queries: list[dict[str, Any]]) -> str:
        if not isinstance(queries, list) or not 1 <= len(queries) <= 5:
            raise AnySearchError("批量搜索需要 1 到 5 个查询。", code="invalid_argument")
        normalized: list[dict[str, Any]] = []
        for item in queries:
            if not isinstance(item, dict):
                raise AnySearchError("批量搜索项格式无效。", code="invalid_argument")
            payload = dict(item)
            payload["query"] = self._validate_query(item.get("query", ""))
            normalized.append(payload)
        return await self._call("batch_search", {"queries": normalized})

    async def extract(self, url: str) -> str:
        self._require_key()
        try:
            safe_url = await validate_public_http_url(url, resolver=self._resolver)
            if self.preflight_redirects:
                safe_url = await resolve_safe_redirects(
                    safe_url,
                    self._probe_redirect,
                    max_redirects=self.max_redirects,
                    resolver=self._resolver,
                )
        except UnsafeUrlError as exc:
            raise AnySearchError(str(exc), code="unsafe_url") from exc
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
            raise AnySearchError(
                f"网页地址安全预检失败：{self._redact(exc)}",
                code="preflight_failed",
            ) from exc
        return await self._call("extract", {"url": safe_url})