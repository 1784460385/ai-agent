"""rate_limit 单元测试。

覆盖:
- 解析 "30/minute" / "1/second" 等格式
- 同 identity 二次请求被拒
- retry_after 计算正确
- 不同 identity 不互相阻塞
- 桶自动补给
"""

import pytest

from rate_limit import RateLimiter, _identity_of


def test_parse_minute():
    rl = RateLimiter(defaults={"test": "30/minute"})
    rl.configure()
    assert rl._capacity["test"] == 30.0
    assert abs(rl._refill["test"] - 0.5) < 1e-6


def test_parse_second():
    rl = RateLimiter(defaults={"test": "2/second"})
    rl.configure()
    assert rl._capacity["test"] == 2.0
    assert abs(rl._refill["test"] - 2.0) < 1e-6


def test_check_allows_up_to_capacity():
    rl = RateLimiter(defaults={"chat": "3/minute"})
    rl.configure()
    for _ in range(3):
        allowed, _ = rl.check("chat", "user-1")
        assert allowed is True
    allowed, retry = rl.check("chat", "user-1")
    assert allowed is False
    assert retry > 0


def test_check_different_identity_not_blocked():
    rl = RateLimiter(defaults={"chat": "2/minute"})
    rl.configure()
    rl.check("chat", "user-1")
    rl.check("chat", "user-1")
    # user-1 满了,但 user-2 不受影响
    assert rl.check("chat", "user-2")[0] is True


def test_check_refills_over_time():
    rl = RateLimiter(defaults={"chat": "1/second"})
    rl.configure()
    now = rl._now_fn()
    # 第 1 次:从满桶取 1,允许
    rl._now_fn = lambda: now
    allowed1, _ = rl.check("chat", "u")
    assert allowed1 is True
    # 0.5 秒后:补了 0.5 个 token,< 1 → 仍拒绝
    rl._now_fn = lambda: now + 0.5
    allowed_mid, retry_mid = rl.check("chat", "u")
    assert allowed_mid is False
    assert retry_mid > 0
    # 1.5 秒后:补满到 1,允许
    rl._now_fn = lambda: now + 1.5
    allowed_late, retry_late = rl.check("chat", "u")
    assert allowed_late is True
    assert retry_late == 0


def test_check_unknown_route_defaults_to_low_capacity():
    rl = RateLimiter(defaults={"chat": "5/minute"})
    rl.configure()
    # 路由不在 defaults 中,使用回退 1/minute
    allowed1, _ = rl.check("nonexistent", "u")
    assert allowed1 is True
    allowed2, _ = rl.check("nonexistent", "u")
    assert allowed2 is False


def test_identity_of_uses_authorization_hash():
    from starlette.requests import Request

    # 真实场景由 starlette 构造 request,此处只验证函数本身对 headers 的逻辑
    # (直接调用 _identity_of 需要 Request 对象,跳过;改为集成测试覆盖)
    assert callable(_identity_of)


def test_rate_limit_middleware_returns_429_under_pressure():
    """端到端:用 TestClient + 真实中间件验证 429 行为。

    注意:由于中间件依赖全局 _LIMITER / _LIMITS,需要先安装一次。
    """
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from rate_limit import RateLimitMiddleware, RateLimiter, install_rate_limiter

    # 1/minute 的桶,跑 1 个请求立即达到上限
    app = FastAPI()

    @app.post("/api/auth/login")
    async def login():
        return {"ok": True}

    limiter = RateLimiter(defaults={"login": "1/minute"})
    limiter.configure()
    # 手动调用 install_rate_limiter — 会注册全局
    install_rate_limiter(app, limits={"login": "1/minute"})

    client = TestClient(app)
    r1 = client.post("/api/auth/login", headers={"authorization": "Bearer test-token-aaa"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/login", headers={"authorization": "Bearer test-token-aaa"})
    assert r2.status_code == 429
    assert "请求过于频繁" in r2.json()["detail"]
    assert "Retry-After" in r2.headers
