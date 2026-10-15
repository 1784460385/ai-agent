"""route_cache 单元测试。

覆盖:
- LRU 容量上限
- TTL 过期
- 不同 key 互相隔离
- route_cache_key 标准化 query(去多余空白 / 大小写)
- route_cache_invalidate_user 按 user 隔离清理
"""

import time

import pytest

from route_cache import (
    TTLCache,
    route_cache_clear,
    route_cache_get,
    route_cache_invalidate_user,
    route_cache_key,
    route_cache_put,
    route_cache_stats,
)


# ---- TTLCache 基础 ----
def test_cache_returns_put_value():
    cache = TTLCache[str, int](max_size=4, ttl_seconds=10)
    cache.put("a", 1)
    assert cache.get("a") == 1


def test_cache_expires_after_ttl():
    now = [1000.0]
    cache = TTLCache[str, int](max_size=4, ttl_seconds=5, _now_fn=lambda: now[0])
    cache.put("a", 1)
    assert cache.get("a") == 1
    now[0] += 6
    assert cache.get("a") is None


def test_cache_lru_eviction():
    cache = TTLCache[str, int](max_size=3, ttl_seconds=60)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    # 访问 a 让它成为最近使用
    cache.get("a")
    cache.put("d", 4)  # 应驱逐 b
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_cache_clear():
    cache = TTLCache[str, int](max_size=4, ttl_seconds=60)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.stats()["size"] == 0


def test_cache_invalidate_single_key():
    cache = TTLCache[str, int](max_size=4, ttl_seconds=60)
    cache.put("a", 1)
    assert cache.invalidate("a") is True
    assert cache.get("a") is None
    assert cache.invalidate("nonexistent") is False


def test_cache_rejects_invalid_params():
    with pytest.raises(ValueError):
        TTLCache[str, int](max_size=0, ttl_seconds=10)
    with pytest.raises(ValueError):
        TTLCache[str, int](max_size=4, ttl_seconds=0)


# ---- route_cache_key ----
def test_route_cache_key_normalizes_whitespace():
    k1 = route_cache_key(1, "  hello  world  ")
    k2 = route_cache_key(1, "hello world")
    assert k1 == k2


def test_route_cache_key_normalizes_case():
    k1 = route_cache_key(1, "Hello World")
    k2 = route_cache_key(1, "hello world")
    assert k1 == k2


def test_route_cache_key_isolated_by_user():
    k1 = route_cache_key(1, "hello")
    k2 = route_cache_key(2, "hello")
    assert k1 != k2


# ---- 单例 cache 接口 ----
def test_singleton_cache_get_put_roundtrip():
    route_cache_clear()
    route_cache_put(1, "测试query", (["hr", "finance"], "rule"))
    assert route_cache_get(1, "测试query") == (["hr", "finance"], "rule")
    route_cache_clear()


def test_invalidate_user_clears_only_user():
    route_cache_clear()
    route_cache_put(1, "q1", (["hr"], "rule"))
    route_cache_put(1, "q2", (["tech"], "rule"))
    route_cache_put(2, "q1", (["finance"], "rule"))
    n = route_cache_invalidate_user(1)
    assert n == 2
    assert route_cache_get(1, "q1") is None
    assert route_cache_get(1, "q2") is None
    # user 2 不受影响
    assert route_cache_get(2, "q1") == (["finance"], "rule")
    route_cache_clear()


def test_singleton_cache_stats():
    route_cache_clear()
    route_cache_put(1, "stats_q", (["hr"], "rule"))
    stats = route_cache_stats()
    assert stats["size"] >= 1
    assert stats["alive"] >= 1
    route_cache_clear()


# ---- 集成:route_query 命中缓存后不再调 LLM ----
def test_route_query_hits_cache_for_repeat(monkeypatch):
    import asyncio

    import router as router_module
    from router import route_query

    route_cache_clear()
    called = {"n": 0}

    async def fake_llm(query, api_key, base_url, model, user_id):
        called["n"] += 1
        return ["hr"]

    monkeypatch.setattr(router_module, "llm_based_route", fake_llm)

    async def run():
        r1 = await route_query("宇宙飞船什么材质", "sk-test", "https://x", "deepseek-flash", user_id=42)
        r2 = await route_query("宇宙飞船什么材质", "sk-test", "https://x", "deepseek-flash", user_id=42)
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1 == (["hr"], "llm")
    assert r2 == (["hr"], "llm")
    assert called["n"] == 1
    route_cache_clear()


def test_route_query_rule_hit_also_cached(monkeypatch):
    """规则命中也走缓存。"""
    import asyncio

    from config import DEPARTMENTS
    import router as router_module
    from router import rule_based_route, route_query

    route_cache_clear()
    called_llm = {"n": 0}

    async def fake_llm(query, api_key, base_url, model, user_id):
        called_llm["n"] += 1
        return ["any"], "llm"

    monkeypatch.setattr(router_module, "llm_based_route", fake_llm)

    # 用 mock 的 catalog 替换真实 folder_map,保证规则可命中
    fake_catalog = {"hr": {"name": "人事部", "keywords": ["年假"]}}
    monkeypatch.setattr(router_module, "folder_map", lambda uid: fake_catalog)

    # 验证 rule_based_route 真的命中
    matched = rule_based_route("我想要年假", user_id=99)
    assert matched == ["hr"]

    async def run():
        r1 = await route_query("我想要年假", "sk-test", "https://x", "deepseek-flash", user_id=99)
        r2 = await route_query("我想要年假", "sk-test", "https://x", "deepseek-flash", user_id=99)
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1[1] == "rule"
    assert r2[1] == "rule"
    # 规则命中也走缓存,LLM 不应被调
    assert called_llm["n"] == 0
    route_cache_clear()
