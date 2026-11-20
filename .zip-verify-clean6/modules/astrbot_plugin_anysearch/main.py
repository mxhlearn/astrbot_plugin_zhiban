from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .client import AnySearchClient, AnySearchError
from .tools import (
    AnySearchBatchTool,
    AnySearchExtractTool,
    AnySearchSearchTool,
    _clamp_max_results,
    _split_csv,
    is_safe_http_url,
)


@register(
    "astrbot_plugin_anysearch",
    "AgIzT",
    "Anysearch实时联网搜索插件为 AstrBot 提供实时网页检索和正文提取能力。知伴适配版默认关闭 LLM 工具，增加 SSRF、响应大小、并发和缓存边界。",
    "0.3",
    "https://github.com/AgIzT/astrbot_plugin_anysearch",
)
class AnySearchPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.client = AnySearchClient(
            api_key=str(self.config.get("api_key", "")),
            timeout=self._get_float("timeout", 20, 1, 120),
            max_response_bytes=self._get_int("max_response_bytes", 1024 * 1024, 1024, 8 * 1024 * 1024),
            max_concurrency=self._get_int("max_concurrency", 2, 1, 8),
            cache_ttl_seconds=self._get_int("cache_ttl_seconds", 120, 0, 3600),
            cache_max_entries=self._get_int("cache_max_entries", 64, 0, 512),
            cache_max_bytes=self._get_int("cache_max_bytes", 2 * 1024 * 1024, 0, 16 * 1024 * 1024),
            max_query_chars=self._get_int("max_query_chars", 2000, 64, 8000),
            preflight_redirects=self._get_bool_config("preflight_redirects", True),
            max_redirects=self._get_int("max_redirects", 3, 0, 10),
        )
        self.command_result_chunk_size = self._get_command_result_chunk_size()
        self.chunk_private_command_results = self._get_bool_config(
            "chunk_private_command_results", True
        )
        self.chunk_group_command_results = self._get_bool_config(
            "chunk_group_command_results", False
        )
        self.tools = []
        if self._get_bool_config("enable_llm_tools", False):
            self.tools = [
                AnySearchSearchTool(client=self.client),
                AnySearchExtractTool(client=self.client),
                AnySearchBatchTool(client=self.client),
            ]
            self.context.add_llm_tools(*self.tools)
        register = getattr(self.context, "register_web_api", None)
        if callable(register):
            register(
                "/astrbot_plugin_anysearch/status",
                self.page_status,
                ["GET"],
                "Anysearch configured state and bounded runtime limits",
            )
        logger.info(
            "AnySearch ready: configured=%s llm_tools=%s",
            self.client.configured,
            bool(self.tools),
        )

    def module_readiness(self) -> dict:
        """Return business readiness without probing the remote service."""
        if not self.client.configured:
            return {
                "state": "not_ready",
                "label": "未配置",
                "detail": "未配置 Anysearch API Key；不会发起联网请求。",
            }
        return {
            "state": "ready",
            "label": "业务可用",
            "detail": "已配置搜索凭据；实际网络可用性在调用时确认。",
        }

    async def page_status(self):
        """Expose only redacted configuration and runtime limits."""
        from quart import jsonify
        return jsonify(
            {
                "status": "ok",
                "data": {
                    **self.client.public_status(),
                    "llm_tools_enabled": bool(self.tools),
                    "readiness": self.module_readiness(),
                },
            }
        )

    async def terminate(self) -> None:
        for tool in self.tools:
            try:
                self.context.provider_manager.llm_tools.remove_func(tool.name)
            except Exception:
                pass
        self.tools = []
        await self.client.close()
        logger.info("AnySearch plugin stopped.")

    @filter.command(
        "anysearch",
        alias={"搜索", "websearch"},
        desc="Anysearch实时联网搜索：支持普通搜索、网页提取和批量搜索。",
    )
    async def search_command(
        self,
        event: AstrMessageEvent,
        query: GreedyStr,
    ):
        query = str(query or "").strip()
        if not query:
            yield event.plain_result(self._usage_text())
            return
        parts = query.split()
        action = parts[0].lower() if parts else ""
        if action in {"help", "帮助", "用法"}:
            yield event.plain_result(self._usage_text())
            return
        if action in {"status", "状态"}:
            yield event.plain_result(self._status_text())
            return
        if action in {"extract", "网页", "提取", "网页提取"}:
            async for result in self._handle_extract(event, " ".join(parts[1:]).strip()):
                yield result
            return
        if action in {"batch", "批量", "批量搜索"}:
            async for result in self._handle_batch(event, query[len(parts[0]) :].strip()):
                yield result
            return
        if is_safe_http_url(query):
            async for result in self._handle_extract(event, query):
                yield result
            return
        try:
            result = await self.client.search(query, max_results=5)
        except AnySearchError as exc:
            yield event.plain_result(f"AnySearch 搜索失败：{exc}")
            return
        for item in self._plain_results(event, result):
            yield item

    def _usage_text(self) -> str:
        return (
            "Anysearch 实时联网搜索用法：\n"
            "/anysearch 关键词\n"
            "/anysearch extract https://example.com/page\n"
            "/anysearch batch 关键词1,关键词2,关键词3\n"
            "/anysearch status\n"
            "中文别名：/搜索 关键词\n"
            "LLM 自动调用默认关闭，需在模块配置中显式启用。"
        )

    def _status_text(self) -> str:
        status = self.client.public_status()
        key_state = "已配置" if status["configured"] else "未配置"
        tools_state = "已启用" if self.tools else "默认关闭"
        return (
            f"Anysearch 状态：API Key {key_state}；LLM 工具 {tools_state}；"
            f"并发上限 {status['max_concurrency']}；响应上限 {status['max_response_bytes']} 字节。"
        )

    def _get_bool_config(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "启用", "开启"}
        return bool(value)

    def _get_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(value, maximum))

    def _get_float(self, key: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(self.config.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(value, maximum))

    def _get_command_result_chunk_size(self) -> int:
        value = self.config.get("command_result_chunk_size", 1200)
        try:
            chunk_size = int(value)
        except (TypeError, ValueError):
            return 1200
        if chunk_size <= 0:
            return 0
        return max(300, min(chunk_size, 1400))

    def _split_plain_text(self, text: str) -> list[str]:
        chunk_size = self.command_result_chunk_size
        if chunk_size <= 0 or len(text) <= chunk_size:
            return [text]
        limit = max(100, chunk_size - 16)
        chunks: list[str] = []
        current = ""

        def flush_current() -> None:
            nonlocal current
            stripped = current.strip()
            if stripped:
                chunks.append(stripped)
            current = ""

        for paragraph in text.split("\n\n"):
            if not paragraph:
                continue
            if len(paragraph) > limit:
                flush_current()
                for line in paragraph.splitlines(keepends=True):
                    while len(line) > limit:
                        segment = line[:limit].strip()
                        if segment:
                            chunks.append(segment)
                        line = line[limit:]
                    if not line.strip():
                        continue
                    if len(current) + len(line) > limit:
                        flush_current()
                    current += line
                continue
            separator = "\n\n" if current else ""
            if len(current) + len(separator) + len(paragraph) > limit:
                flush_current()
            current = f"{current}{separator}{paragraph}" if current else paragraph
        flush_current()
        if len(chunks) <= 1:
            return chunks or [text]
        total = len(chunks)
        return [f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, 1)]

    def _should_split_command_result(self, event: AstrMessageEvent, text: str) -> bool:
        if self.command_result_chunk_size <= 0 or len(text) <= self.command_result_chunk_size:
            return False
        if event.get_platform_name() != "aiocqhttp":
            return False
        if event.get_group_id():
            return self.chunk_group_command_results
        return self.chunk_private_command_results

    def _plain_results(self, event: AstrMessageEvent, text: str):
        if not self._should_split_command_result(event, text):
            yield event.plain_result(text)
            return
        for chunk in self._split_plain_text(text):
            yield event.plain_result(chunk)

    async def _handle_extract(self, event: AstrMessageEvent, url: str):
        url = url.strip()
        if not url:
            yield event.plain_result("用法：/anysearch extract https://example.com/page")
            return
        if not is_safe_http_url(url):
            yield event.plain_result("只允许提取公开的 http(s) 网页地址。")
            return
        try:
            result = await self.client.extract(url)
        except AnySearchError as exc:
            yield event.plain_result(f"AnySearch 提取失败：{exc}")
            return
        for item in self._plain_results(event, result):
            yield item

    async def _handle_batch(self, event: AstrMessageEvent, queries: str):
        items = _split_csv(queries)
        if not items:
            yield event.plain_result("用法：/anysearch batch 关键词1,关键词2,关键词3")
            return
        query_objects = [
            {"query": item, "max_results": _clamp_max_results(3)}
            for item in items[:5]
        ]
        try:
            result = await self.client.batch_search(query_objects)
        except AnySearchError as exc:
            yield event.plain_result(f"AnySearch 批量搜索失败：{exc}")
            return
        for item in self._plain_results(event, result):
            yield item