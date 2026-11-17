from __future__ import annotations

import socket

import pytest

from astrbot_plugin_anysearch.security import (
    PublicResolver,
    UnsafeUrlError,
    resolve_safe_redirects,
    validate_public_http_url,
)


def _resolver_for(mapping):
    async def resolver(host, port, *, type=socket.SOCK_STREAM):
        address = mapping[host]
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
        return [(family, type, socket.IPPROTO_TCP, "", sockaddr)]

    return resolver


@pytest.mark.asyncio
async def test_rejects_non_http_credentials_and_private_literals():
    for url in (
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://user:pass@example.com/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://localhost/",
        "http://service.internal/",
        "http://example.com\\@127.0.0.1/",
    ):
        with pytest.raises(UnsafeUrlError):
            await validate_public_http_url(url, resolver=_resolver_for({}))


@pytest.mark.asyncio
async def test_dns_must_resolve_only_to_global_addresses():
    resolver = _resolver_for({"public.example": "93.184.216.34"})
    assert await validate_public_http_url("https://public.example/path?q=1", resolver=resolver) == (
        "https://public.example/path?q=1"
    )

    private = _resolver_for({"mixed.example": "127.0.0.1"})
    with pytest.raises(UnsafeUrlError):
        await validate_public_http_url("https://mixed.example/", resolver=private)


@pytest.mark.asyncio
async def test_redirect_chain_validates_every_hop_and_rejects_private_target():
    resolver = _resolver_for(
        {
            "start.example": "93.184.216.34",
            "final.example": "93.184.216.35",
        }
    )

    async def request(url):
        if "start.example" in url:
            return 302, {"Location": "https://final.example/final"}
        return 200, {}

    assert await resolve_safe_redirects(
        "https://start.example/start", request, resolver=resolver
    ) == "https://final.example/final"

    called = []

    async def redirect_private(url):
        called.append(url)
        return 302, {"Location": "http://127.0.0.1/admin"}

    with pytest.raises(UnsafeUrlError):
        await resolve_safe_redirects(
            "https://start.example/start", redirect_private, resolver=resolver
        )
    assert called == ["https://start.example/start"]


@pytest.mark.asyncio
async def test_redirect_loop_and_limit_are_bounded():
    resolver = _resolver_for({"a.example": "93.184.216.34"})

    async def loop(url):
        return 302, {"Location": "https://a.example/again"}

    with pytest.raises(UnsafeUrlError, match="循环"):
        await resolve_safe_redirects("https://a.example/start", loop, resolver=resolver)

    async def forever(url):
        return 302, {"Location": "https://a.example/next"}

    with pytest.raises(UnsafeUrlError, match="次数"):
        await resolve_safe_redirects(
            "https://a.example/start", forever, max_redirects=1, resolver=resolver
        )
@pytest.mark.asyncio
async def test_https_downgrade_redirect_is_rejected():
    resolver = _resolver_for({"a.example": "93.184.216.34"})

    async def downgrade(url):
        return 302, {"Location": "http://a.example/plain"}

    with pytest.raises(UnsafeUrlError, match="降级"):
        await resolve_safe_redirects("https://a.example/start", downgrade, resolver=resolver)
@pytest.mark.asyncio
async def test_connect_time_resolver_rejects_private_dns_answers():
    public = PublicResolver(_resolver_for({"public.example": "93.184.216.34"}))
    results = await public.resolve("public.example", 443)
    assert results[0]["host"] == "93.184.216.34"

    private = PublicResolver(_resolver_for({"private.example": "10.0.0.8"}))
    with pytest.raises(OSError, match="non-public"):
        await private.resolve("private.example", 443)