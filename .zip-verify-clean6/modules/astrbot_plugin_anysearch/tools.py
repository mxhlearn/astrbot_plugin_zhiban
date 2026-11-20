from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent

from .client import AnySearchClient, AnySearchError
from .security import UnsafeUrlError, _parse_http_url


CONTENT_TYPES = {
    "web",
    "news",
    "code",
    "doc",
    "academic",
    "data",
    "image",
    "video",
    "audio",
}
FRESHNESS_VALUES = {"day", "week", "month", "year"}


def _split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in text.split(",") if part.strip()]


def _clamp_max_results(value: Any, default: int = 5) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, 20))


def _normalize_content_types(value: Any) -> list[str]:
    return [item for item in _split_csv(value) if item in CONTENT_TYPES]


def is_safe_http_url(url: str) -> bool:
    """Cheap literal check; client.extract still performs DNS/redirect validation."""

    try:
        _parse_http_url(url)
    except (TypeError, ValueError, UnsafeUrlError):
        return False
    return True


def _tool_error(exc: AnySearchError) -> str:
    if exc.code == "not_configured":
        return "Anysearch 未配置：请先填写 API Key 并显式启用 LLM 工具。"
    return f"错误：{exc}"


@dataclass
class AnySearchSearchTool(FunctionTool):
    client: AnySearchClient = field(repr=False, default_factory=AnySearchClient)
    name: str = "anysearch_search"
    description: str = (
        "使用 Anysearch 进行实时联网搜索。适合查询最新事实、新闻、文档、资料检索和一般网页信息。"
        "只有在用户明确需要外部最新信息时才调用。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "必填。搜索关键词或自然语言问题。"},
                "max_results": {
                    "type": "integer",
                    "description": "可选。返回结果数量，范围 1-20，默认 5。",
                },
                "freshness": {
                    "type": "string",
                    "description": "可选。day、week、month、year 之一。",
                },
                "content_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。web、news、code、doc、academic、data、image、video、audio。",
                },
            },
            "required": ["query"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        query: str,
        max_results: int = 5,
        freshness: str = "",
        content_types: list[str] | str | None = None,
    ) -> str:
        _ = event
        query = str(query or "").strip()
        if not query:
            return "错误：query 不能为空。"
        freshness = freshness if freshness in FRESHNESS_VALUES else ""
        try:
            return await self.client.search(
                query,
                max_results=_clamp_max_results(max_results, default=5),
                freshness=freshness,
                content_types=_normalize_content_types(content_types),
            )
        except AnySearchError as exc:
            return _tool_error(exc)


@dataclass
class AnySearchExtractTool(FunctionTool):
    client: AnySearchClient = field(repr=False, default_factory=AnySearchClient)
    name: str = "anysearch_extract"
    description: str = (
        "使用 Anysearch 提取公开网页的可读 Markdown 正文。"
        "不要用于本地地址、内网地址、私有页面或包含敏感信息的 URL。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "必填。要提取正文的公开 http(s) 网页 URL。",
                }
            },
            "required": ["url"],
        }
    )

    async def run(self, event: AstrMessageEvent, url: str) -> str:
        _ = event
        url = str(url or "").strip()
        if not is_safe_http_url(url):
            return "错误：只允许公开的 http(s) URL。"
        try:
            return await self.client.extract(url)
        except AnySearchError as exc:
            return _tool_error(exc)


@dataclass
class AnySearchBatchTool(FunctionTool):
    client: AnySearchClient = field(repr=False, default_factory=AnySearchClient)
    name: str = "anysearch_batch_search"
    description: str = "使用 Anysearch 并行执行 1 到 5 个搜索查询。"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "string",
                    "description": "必填。JSON 数组或用逗号分隔的多个查询。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "可选。每个查询返回结果数，默认 5。",
                },
                "freshness": {"type": "string", "description": "可选。day、week、month、year。"},
                "content_types": {"type": "string", "description": "可选。逗号分隔的内容类型。"},
            },
            "required": ["queries"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        queries: str,
        max_results: int = 5,
        freshness: str = "",
        content_types: str = "",
    ) -> str:
        _ = event
        return await self._run(queries, max_results, freshness, content_types)

    async def _run(
        self,
        queries: str,
        max_results: int,
        freshness: str,
        content_types: str,
    ) -> str:
        items = self._parse_queries(queries)
        if not items:
            return "错误：queries 至少需要包含一个查询。"
        normalized: list[dict[str, Any]] = []
        for item in items[:5]:
            query = str(item.get("query", "")).strip()
            if not query:
                continue
            payload: dict[str, Any] = {
                "query": query,
                "max_results": _clamp_max_results(item.get("max_results", max_results)),
            }
            item_freshness = str(item.get("freshness", freshness)).strip()
            if item_freshness in FRESHNESS_VALUES:
                payload["freshness"] = item_freshness
            item_content_types = _normalize_content_types(
                item.get("content_types", content_types)
            )
            if item_content_types:
                payload["content_types"] = item_content_types
            normalized.append(payload)
        if not normalized:
            return "错误：queries 需要包含非空查询文本。"
        try:
            return await self.client.batch_search(normalized)
        except AnySearchError as exc:
            return _tool_error(exc)

    @staticmethod
    def _parse_queries(value: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [
                    item if isinstance(item, dict) else {"query": str(item)}
                    for item in parsed
                ]
            return [{"query": str(parsed)}]
        except (json.JSONDecodeError, TypeError):
            return [{"query": item} for item in _split_csv(value)]