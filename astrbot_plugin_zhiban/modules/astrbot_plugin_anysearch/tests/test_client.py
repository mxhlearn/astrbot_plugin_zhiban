from __future__ import annotations

import asyncio
import json
import socket

import pytest

from astrbot_plugin_anysearch.client import AnySearchClient, AnySearchError


class FakeContent:
    def __init__(self, body: bytes):
        self.body = body

    async def iter_chunked(self, size):
        for index in range(0, len(self.body), size):
            await asyncio.sleep(0)
            yield self.body[index : index + size]


class FakeResponse:
    def __init__(
        self,
        *,
        status=200,
        body=b"",
        headers=None,
        session=None,
        delay=0,
    ):
        self.status = status
        self.headers = headers or {}
        self.content = FakeContent(body)
        self._body = body
        self._session = session
        self._delay = delay

    async def __aenter__(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is not None:
            self._session.active -= 1
        return False

    async def read(self):
        return self._body


class FakeSession:
    def __init__(self, responses=None, *, delay=0):
        self.closed = False
        self.posts = []
        self.gets = []
        self.active = 0
        self.max_active = 0
        self.delay = delay
        self.responses = list(responses or [])

    def _response(self, body=b"", status=200, headers=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        return FakeResponse(
            status=status,
            body=body,
            headers=headers,
            session=self,
            delay=self.delay,
        )

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self.responses:
            status, body, headers = self.responses.pop(0)
            return self._response(body=body, status=status, headers=headers)
        body = json.dumps(
            {"result": {"content": [{"type": "text", "text": "search-result"}]}}
        ).encode()
        return self._response(body=body)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self._response(status=200, body=b"")

    async def close(self):
        self.closed = True


def _public_resolver(mapping):
    async def resolver(host, port, *, type=socket.SOCK_STREAM):
        address = mapping[host]
        sockaddr = (address, port)
        return [(socket.AF_INET, type, socket.IPPROTO_TCP, "", sockaddr)]

    return resolver


@pytest.mark.asyncio
async def test_missing_key_never_creates_session_or_network_request():
    created = []

    def factory():
        created.append(True)
        return FakeSession()

    client = AnySearchClient(api_key="", session_factory=factory)
    with pytest.raises(AnySearchError) as error:
        await client.search("latest news")
    assert error.value.code == "not_configured"
    assert created == []
    assert "api_key" not in client.public_status()


@pytest.mark.asyncio
async def test_search_uses_bounded_session_and_caches_success():
    session = FakeSession()
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        cache_ttl_seconds=120,
        preflight_redirects=False,
    )
    first = await client.search("same query")
    second = await client.search("same query")
    assert first == second == "search-result"
    assert len(session.posts) == 1
    _, request = session.posts[0]
    assert request["headers"]["Authorization"] == "Bearer secret-value"
    assert "secret-value" not in repr(client)
    assert "secret-value" not in json.dumps(client.public_status(), ensure_ascii=False)
    await client.close()
    assert session.closed is True


@pytest.mark.asyncio
async def test_response_size_limit_is_enforced_before_use():
    body = b"x" * 3000
    session = FakeSession(responses=[(200, body, {"Content-Length": str(len(body))})])
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        max_response_bytes=2048,
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.search("large")
    assert error.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_http_error_redacts_key():
    session = FakeSession(
        responses=[(401, b"bad api_key=secret-value Bearer secret-value", {})]
    )
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.search("bad")
    message = str(error.value)
    assert "secret-value" not in message
    assert "[REDACTED]" in message


@pytest.mark.asyncio
async def test_concurrency_limit_serializes_requests():
    session = FakeSession(delay=0.02)
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        max_concurrency=1,
        preflight_redirects=False,
        cache_ttl_seconds=0,
    )
    await asyncio.gather(client.search("one"), client.search("two"))
    assert session.max_active == 1


@pytest.mark.asyncio
async def test_extract_preflights_redirect_then_sends_final_public_url():
    response_body = json.dumps(
        {"result": {"content": [{"type": "text", "text": "page"}]}}
    ).encode()
    session = FakeSession(responses=[(200, response_body, {})])
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        resolver=_public_resolver(
            {"start.example": "93.184.216.34", "final.example": "93.184.216.35"}
        ),
        preflight_redirects=True,
    )

    def fake_get(url, **kwargs):
        session.gets.append((url, kwargs))
        if url == "https://start.example/start":
            return FakeResponse(
                status=302,
                body=b"",
                headers={"Location": "https://final.example/final"},
                session=session,
            )
        return FakeResponse(status=200, body=b"", session=session)

    session.get = fake_get
    assert await client.extract("https://start.example/start") == "page"
    assert session.gets[0][0] == "https://start.example/start"
    payload = session.posts[0][1]["json"]
    assert payload["params"]["arguments"]["url"] == "https://final.example/final"


@pytest.mark.asyncio
async def test_private_extract_is_rejected_without_post():
    session = FakeSession()
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.extract("http://169.254.169.254/latest/meta-data/")
    assert error.value.code == "unsafe_url"
    assert session.posts == []
@pytest.mark.asyncio
async def test_timeout_is_reported_without_leaking_secret():
    session = FakeSession()

    def timeout_post(*args, **kwargs):
        raise asyncio.TimeoutError()

    session.post = timeout_post
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.search("timeout")
    assert error.value.code == "timeout"
    assert "secret-value" not in str(error.value)
@pytest.mark.asyncio
async def test_api_redirect_is_rejected():
    session = FakeSession(responses=[(302, b"", {"Location": "https://elsewhere.example"})])
    client = AnySearchClient(
        api_key="secret-value",
        session_factory=lambda: session,
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.search("redirect")
    assert error.value.code == "redirect_rejected"


@pytest.mark.asyncio
async def test_query_length_limit_fails_before_network():
    created = []
    client = AnySearchClient(
        api_key="secret-value",
        max_query_chars=64,
        session_factory=lambda: created.append(True) or FakeSession(),
        preflight_redirects=False,
    )
    with pytest.raises(AnySearchError) as error:
        await client.search("x" * 65)
    assert error.value.code == "invalid_argument"
    assert created == []