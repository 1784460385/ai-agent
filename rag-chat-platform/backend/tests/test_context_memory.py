"""context_memory 模块的纯函数测试。

集成测试(需要真实数据库 + Mock DeepSeek)放在 test_context_memory_integration.py。
这里只测纯函数:
- estimate_tokens
- _should_summarize
- _trim_pending
- _messages_from_turns
- split_turns
- _fallback_query
"""

import types

from context_memory import (
    _fallback_query,
    _messages_from_turns,
    _should_summarize,
    _trim_pending,
    estimate_tokens,
    split_turns,
)


def _row(question: str = "", answer: str = "", rid: int = 1, attachments: str | None = None):
    """构造一个 ChatHistory-like 对象(只测纯函数,不查 ORM 属性)。"""
    return types.SimpleNamespace(
        id=rid,
        question=question,
        answer=answer,
        attachments=attachments,
    )


# ---- estimate_tokens ----
def test_estimate_tokens_chinese():
    """中文按 2 字符 ≈ 1 token 估算。"""
    assert estimate_tokens("你好") == 1
    assert estimate_tokens("你好世界") == 2
    assert estimate_tokens("你好世界你好世界") == 4


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_tokens("   ") == 0


def test_estimate_tokens_short_string():
    """不足 2 字符也算 1 token。"""
    assert estimate_tokens("a") == 1


# ---- _should_summarize ----
def test_should_summarize_below_threshold():
    """单行 token 远低于阈值时,不应触发摘要(只看 token)。"""
    rows = [_row(rid=1, question="短", answer="短答")]
    assert _should_summarize(rows) is False


def test_should_summarize_triggers_at_token_threshold():
    """单条 token ≥ 800 时,即使只有 1 行也触发。"""
    rows = [_row(rid=1, question="问题", answer="x" * 2000)]  # ≈1000 token
    assert _should_summarize(rows) is True


def test_should_summarize_triggers_at_turn_threshold():
    """行数 ≥ SUMMARY_TRIGGER_TURNS(=2) 时触发,与 token 无关。"""
    rows = [_row(rid=i, question="短", answer="短") for i in range(1, 4)]
    assert _should_summarize(rows) is True


def test_should_summarize_empty():
    assert _should_summarize([]) is False


# ---- _trim_pending ----
def test_trim_pending_keeps_recent_when_over_budget():
    """超过 token 上限时只保留较新的若干行。"""
    long = "x" * 2000
    rows = [
        _row(rid=1, question="a", answer=long),
        _row(rid=2, question="b", answer=long),
        _row(rid=3, question="c", answer="短"),  # 这条较新
    ]
    trimmed = _trim_pending(rows)
    # 最近那条(c)肯定保留;更早的 a/b 可能被裁
    assert trimmed[-1].id == 3


def test_trim_pending_returns_empty_for_empty():
    assert _trim_pending([]) == []


# ---- _messages_from_turns ----
def test_messages_from_turns_basic():
    rows = [_row(question="问 1", answer="答 1", rid=1), _row(question="问 2", answer="答 2", rid=2)]
    msgs = _messages_from_turns(rows)
    assert msgs == [
        {"role": "user", "content": "问 1"},
        {"role": "assistant", "content": "答 1"},
        {"role": "user", "content": "问 2"},
        {"role": "assistant", "content": "答 2"},
    ]


def test_messages_from_turns_empty_answer():
    rows = [_row(question="问", answer="", rid=1)]
    msgs = _messages_from_turns(rows)
    assert msgs == [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": ""},
    ]


# ---- split_turns ----
def test_split_turns_basic():
    rows = [_row(rid=i) for i in range(1, 6)]
    pending, recent = split_turns(rows, summary_last_id=0)
    # RECENT_CONTEXT_TURNS=2: recent 取最后 2 轮(rid=4,5)
    assert [r.id for r in recent] == [4, 5]
    # pending = older 中 summary 之后的所有 → rid=1,2,3
    assert [r.id for r in pending] == [1, 2, 3]


def test_split_turns_respects_summary_pointer():
    rows = [_row(rid=i) for i in range(1, 6)]
    pending, recent = split_turns(rows, summary_last_id=2)
    # summary 已经包含了 rid ≤ 2 的,所以 pending 只剩 rid=3
    assert [r.id for r in pending] == [3]
    assert [r.id for r in recent] == [4, 5]


def test_split_turns_fewer_than_recent():
    rows = [_row(rid=1), _row(rid=2)]
    pending, recent = split_turns(rows, summary_last_id=0)
    # rows 只有 2 条,recent 取全部,pending 为空
    assert [r.id for r in recent] == [1, 2]
    assert pending == []


def test_split_turns_empty():
    pending, recent = split_turns([], summary_last_id=0)
    assert pending == []
    assert recent == []


# ---- _fallback_query ----
def test_fallback_query_with_previous_user_turn():
    recent = [_row(question="之前的提问", answer="之前的回答"), _row(question="最近的提问", answer="最近的回答")]
    result = _fallback_query("它怎么用？", recent)
    # 应该拼接最近的用户问题 + 当前问题
    assert "最近的提问" in result
    assert "它怎么用" in result


def test_fallback_query_when_same_as_recent():
    """当前问题与最近一轮相同,不应该重复拼接。"""
    recent = [_row(question="同一句话")]
    result = _fallback_query("同一句话", recent)
    assert result == "同一句话"


def test_fallback_query_no_recent():
    """没有 recent 时直接返回原问题。"""
    result = _fallback_query("独立问题", [])
    assert result == "独立问题"


def test_fallback_query_truncates_long_input():
    """长输入截断到 300 字。"""
    long_q = "x" * 500
    result = _fallback_query(long_q, [])
    assert len(result) == 500  # 直接返回原 query 不截断,因为 _fallback_query 在 recent 拼接时才会截
    # 触发截断的场景:recent 有内容
    recent = [_row(question="短")]
    long_recent = _fallback_query(long_q, recent)
    assert len(long_recent) <= 300