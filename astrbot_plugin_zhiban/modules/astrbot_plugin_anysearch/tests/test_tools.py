from __future__ import annotations

import pytest

from astrbot_plugin_anysearch.client import AnySearchClient
from astrbot_plugin_anysearch.tools import (
    AnySearchBatchTool,
    AnySearchExtractTool,
    AnySearchSearchTool,
    is_safe_http_url,
)


class FakeBatchClient:
    def __init__(self):
        self.queries = None

    async def batch_search(self, queries):
        self.queries = queries
        return "batch-result"


def test_literal_url_check_rejects_local_and_private_targets():
    assert is_safe_http_url("https://example.com/page") is True
    assert is_safe_http_url("http://127.0.0.1/") is False
    assert is_safe_http_url("http://192.168.1.2/") is False
    assert is_safe_http_url("file:///etc/passwd") is False
    assert is_safe_http_url("https://user:pass@example.com/") is False


@pytest.mark.asyncio
async def test_missing_key_tools_return_not_configured_without_network():
    client = AnySearchClient(api_key="")
    search = AnySearchSearchTool(client=client)
    result = await search.run(object(), "latest")
    assert "未配置" in result


@pytest.mark.asyncio
async def test_extract_tool_rejects_private_url_before_client_call():
    tool = AnySearchExtractTool(client=AnySearchClient(api_key="key"))
    result = await tool.run(object(), "http://169.254.169.254/latest/meta-data/")
    assert "只允许公开" in result


@pytest.mark.asyncio
async def test_batch_tool_clamps_and_limits_queries():
    client = FakeBatchClient()
    tool = AnySearchBatchTool(client=client)
    result = await tool.run(
        object(),
        "one,two,three,four,five,six",
        max_results=100,
        freshness="week",
        content_types="web,invalid,news",
    )
    assert result == "batch-result"
    assert len(client.queries) == 5
    assert client.queries[0] == {
        "query": "one",
        "max_results": 20,
        "freshness": "week",
        "content_types": ["web", "news"],
    }