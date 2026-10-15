"""进程内 LRU + TTL 缓存。

用于:
- 路由结果缓存(route_query)
- 任何"重复 query 概率高、结果可短暂复用"的纯函数

特性:
- LRU 驱逐(避免内存无限增长)
- TTL 过期(默认 5 分钟,防止用户改了文件夹/部门后还是旧路由)
- 线程安全(主进程内)
- 可注入 _now_fn / _max_size 便于测试

不适用:
- 需要跨进程共享的(应换 Redis)
- 数据一致性敏感的(索引刚建好不应立即看到陈旧路由 — TTL 必须短)
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any, Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """最简单的 LRU + TTL 实现。

    复杂度: get/put 都是 O(1) (OrderedDict 维护顺序)。
    """

    def __init__(
        self,
        max_size: int = 512,
        ttl_seconds: float = 300.0,
        *,
        _now_fn: Callable[[], float] = time.monotonic,
    ):
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._now = _now_fn
        self._data: "OrderedDict[K, tuple[V, float]]" = OrderedDict()

    def get(self, key: K, *, default: V | None = None) -> V | None:
        item = self._data.get(key)
        if item is None:
            return default
        value, expires_at = item
        if expires_at <= self._now():
            # 过期 → 驱逐
            self._data.pop(key, None)
            return default
        # 命中 → 移动到末尾(标记为最近使用)
        self._data.move_to_end(key)
        return value

    def put(self, key: K, value: V) -> None:
        expires_at = self._now() + self._ttl
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (value, expires_at)
        # 容量控制
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def invalidate(self, key: K) -> bool:
        return self._data.pop(key, None) is not None

    def clear(self) -> None:
        self._data.clear()

    def stats(self) -> dict[str, Any]:
        now = self._now()
        alive = sum(1 for _, exp in self._data.values() if exp > now)
        return {
            "size": len(self._data),
            "alive": alive,
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
        }


# ---- 路由专用 ----
# 单例缓存。模块级共享,任何用户的同 query 都可能命中 — 路由结果本身只依赖
# 用户的文件夹配置(folder_map),而 folder_map 由 user_id 决定,所以 key 必须
# 含 user_id + query。
_route_cache: TTLCache[tuple[int, str], tuple[list[str], str]] = TTLCache(
    max_size=2048,
    ttl_seconds=300.0,
)


def route_cache_key(user_id: int, query: str) -> tuple[int, str]:
    """生成路由缓存 key。query 标准化(去多余空白)以提高命中率。"""
    normalized = " ".join((query or "").split()).lower()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return (user_id, digest)


def route_cache_get(user_id: int, query: str) -> tuple[list[str], str] | None:
    return _route_cache.get(route_cache_key(user_id, query))


def route_cache_put(user_id: int, query: str, result: tuple[list[str], str]) -> None:
    _route_cache.put(route_cache_key(user_id, query), result)


def route_cache_invalidate_user(user_id: int) -> int:
    """用户改了文件夹配置后调用,清掉该用户所有路由缓存。"""
    n = 0
    for key in list(_route_cache._data.keys()):
        uid, _ = key
        if uid == user_id:
            _route_cache.invalidate(key)
            n += 1
    return n


def route_cache_clear() -> None:
    _route_cache.clear()


def route_cache_stats() -> dict[str, Any]:
    return _route_cache.stats()
