from astrbot_plugin_anysearch.client import TTLCache


def test_cache_enforces_ttl_entry_and_byte_limits():
    now = [0.0]
    cache = TTLCache(
        ttl_seconds=10,
        max_entries=2,
        max_bytes=10,
        clock=lambda: now[0],
    )
    assert cache.put("a", "12345") is True
    assert cache.put("b", "67890") is True
    assert cache.get("a") == "12345"
    assert cache.put("c", "abcde") is True
    assert cache.get("b") is None
    assert cache.get("a") == "12345"
    assert cache.get("c") == "abcde"
    assert cache.put("large", "x" * 11) is False
    now[0] = 11
    assert cache.get("a") is None
    assert cache.size_bytes == 0