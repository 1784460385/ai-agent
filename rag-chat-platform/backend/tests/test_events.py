"""SSE 事件常量测试。"""

import pytest

from events import (
    EVENT_CONVERSATION,
    EVENT_DELTA,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_ROUTER,
    EVENT_SOURCES,
    ROUTER_VIA_LLM,
    ROUTER_VIA_RULE,
    is_known_event,
)


def test_event_constants_are_strings():
    """常量必须是字符串,前端可序列化。"""
    for value in (
        EVENT_CONVERSATION,
        EVENT_ROUTER,
        EVENT_SOURCES,
        EVENT_DELTA,
        EVENT_DONE,
        EVENT_ERROR,
    ):
        assert isinstance(value, str)


def test_event_constants_distinct():
    """事件 type 必须彼此不同,避免路由冲突。"""
    seen = {
        EVENT_CONVERSATION,
        EVENT_ROUTER,
        EVENT_SOURCES,
        EVENT_DELTA,
        EVENT_DONE,
        EVENT_ERROR,
    }
    assert len(seen) == 6


def test_router_via_constants():
    assert ROUTER_VIA_RULE == "rule"
    assert ROUTER_VIA_LLM == "llm"


@pytest.mark.parametrize(
    "event_type",
    [
        EVENT_CONVERSATION,
        EVENT_ROUTER,
        EVENT_SOURCES,
        EVENT_DELTA,
        EVENT_DONE,
        EVENT_ERROR,
    ],
)
def test_is_known_event_accepts_known(event_type: str):
    assert is_known_event(event_type) is True


@pytest.mark.parametrize("event_type", ["unknown", "", "DONE", "Delta"])
def test_is_known_event_rejects_unknown(event_type: str):
    assert is_known_event(event_type) is False