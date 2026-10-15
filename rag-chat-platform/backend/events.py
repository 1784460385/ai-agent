"""SSE 事件类型与字段名常量。

集中在这里是为了让前端 TypeScript 和后端 Python 同步命名,避免拼写错误。
前端如果用 TypeScript,可以把同名字段复制过去;字段含义变更时先改这里再同步。
"""

from __future__ import annotations

from typing import Final, Literal

# ---- 事件类型(type 字段取值) ----
EVENT_CONVERSATION: Final = "conversation"
EVENT_ROUTER: Final = "router"
EVENT_SOURCES: Final = "sources"
EVENT_DELTA: Final = "delta"
EVENT_DONE: Final = "done"
EVENT_ERROR: Final = "error"

ChatEventType = Literal[
    "conversation",
    "router",
    "sources",
    "delta",
    "done",
    "error",
]

# ---- router 事件 via 字段 ----
ROUTER_VIA_RULE: Final = "rule"
ROUTER_VIA_LLM: Final = "llm"
RouterVia = Literal["rule", "llm"]


def is_known_event(event_type: str) -> bool:
    """校验事件类型是否在已知列表中。供测试与解析器使用。"""
    return event_type in {
        EVENT_CONVERSATION,
        EVENT_ROUTER,
        EVENT_SOURCES,
        EVENT_DELTA,
        EVENT_DONE,
        EVENT_ERROR,
    }