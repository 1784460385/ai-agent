"""轻量级进程内限速(token bucket)。

设计:
- 在主进程内存里维护每个 (route, identity) 的桶
- 默认按 route 名称区分;identity 用 X-Forwarded-For > token 主题 > IP
- 命中限速返回 429 + Retry-After + 统一文案(走 safe_strings.public_error)
- 同一进程的多个 worker 各自一份;真正多实例需要外部存储(此处先不做)

用法:
    app.state.limiter = RateLimiter(defaults={"chat": "30/minute"})
    install_rate_limiter(app)

关键接口的限速配置(可在 defaults 中调整):
- chat: 30/minute(每位用户每分钟最多 30 次对话)
- chat_stream: 10/minute(流式接口更敏感)
- login: 5/minute(防爆破)
- upload: 10/minute
- index: 1/minute(全量重建很贵)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from safe_strings import public_error

DEFAULT_LIMITS = {
    "chat": "30/minute",
    "chat_stream": "30/minute",
    "login": "5/minute",
    "upload": "10/minute",
    "index": "1/minute",
}


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


@dataclass
class RateLimiter:
    """简单的 token bucket。capacity = 突发,refill_per_sec = 平均速率。

    format:
        "30/minute"  -> 30 次/60 秒
        "5/minute"   -> 5 次/60 秒
        "1/second"   -> 1 次/1 秒
    """

    defaults: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    _capacity: dict[str, float] = field(default_factory=dict)
    _refill: dict[str, float] = field(default_factory=dict)
    _buckets: dict[tuple, _Bucket] = field(default_factory=dict)
    _now_fn: Callable[[], float] = time.perf_counter

    def _parse(self, spec: str) -> tuple[float, float]:
        """返回 (capacity, refill_per_sec)。"""
        try:
            count_str, unit = spec.split("/")
            count = float(count_str.strip())
            unit = unit.strip().lower()
        except (ValueError, AttributeError):
            return 1.0, 1.0 / 60
        seconds = {
            "second": 1,
            "sec": 1,
            "s": 1,
            "minute": 60,
            "min": 60,
            "m": 60,
            "hour": 3600,
            "h": 3600,
            "day": 86400,
            "d": 86400,
        }.get(unit, 60)
        return count, count / seconds

    def configure(self) -> None:
        for name, spec in self.defaults.items():
            cap, refill = self._parse(spec)
            self._capacity[name] = cap
            self._refill[name] = refill

    def check(self, name: str, identity: str) -> tuple[bool, float]:
        """返回 (allow, retry_after_seconds)。"""
        self.configure()
        capacity = self._capacity.get(name, 1.0)
        refill = self._refill.get(name, 1.0 / 60)
        now = self._now_fn()
        key = (name, identity)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=capacity, last_refill=now)
            self._buckets[key] = bucket
        # 补充 token
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(capacity, bucket.tokens + elapsed * refill)
            bucket.last_refill = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return True, 0.0
        need = 1 - bucket.tokens
        retry = need / refill if refill > 0 else 1.0
        return False, max(retry, 0.1)


# ---- 配套中间件 ----
_ROUTE_KEYS = {
    "/api/chat": "chat_stream",
    "/api/chat/stream": "chat_stream",
    "/api/auth/login": "login",
    "/api/upload": "upload",
    "/api/index": "index",
}


def _identity_of(request: Request) -> str:
    """取请求身份,优先级:
    1. Authorization 中 token 的 sha256(避免每条请求都解析完整 JWT)
    2. X-Forwarded-For 头
    3. 客户端 IP
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and len(auth) > 7:
        token = auth.split(" ", 1)[1].strip()
        if token:
            return "tok:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return "ip:" + xff.split(",")[0].strip()
    if request.client and request.client.host:
        return "ip:" + request.client.host
    return "ip:unknown"


_LIMITS: dict[str, str] = {}
_LIMITER: RateLimiter | None = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按 (route, identity) 限速。命中限速返回 429。"""

    async def dispatch(self, request: Request, call_next):
        if _LIMITER is None:
            return await call_next(request)
        path = request.url.path
        bucket_name = _ROUTE_KEYS.get(path)
        if not bucket_name or bucket_name not in _LIMITS:
            return await call_next(request)
        identity = _identity_of(request)
        allowed, retry_after = _LIMITER.check(bucket_name, identity)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": public_error("rate_limited")},
                headers={"Retry-After": f"{int(retry_after) + 1}"},
            )
        return await call_next(request)


def install_rate_limiter(app, *, limits: dict[str, str] | None = None) -> RateLimiter:
    """在 FastAPI app 上注册限速中间件。

    调用一次即可。返回 RateLimiter 实例,便于测试时重置 state 或注入 mock。
    """
    global _LIMITER, _LIMITS
    _LIMITS = dict(limits or DEFAULT_LIMITS)
    _LIMITER = RateLimiter(defaults=_LIMITS)
    _LIMITER.configure()
    app.add_middleware(RateLimitMiddleware)
    return _LIMITER
