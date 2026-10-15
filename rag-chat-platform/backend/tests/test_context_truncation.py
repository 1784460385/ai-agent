"""上下文动态收敛测试。

覆盖 _truncate_by_chars 的所有边界:
- 总字符数未达上限:全部保留
- 累加字符数到上限停止
- 单条内容超过剩余预算:截断(200 字符以下的不保留,避免拼半句)
- max_chars=0 退化
- 累计字符数返回正确
"""

import pytest

from vector_store import _truncate_by_chars


def _hit(content: str, hit_id: str = "x") -> dict:
    return {"id": hit_id, "content": content, "source": "src", "department": "d", "department_name": "部门"}


def test_truncate_keeps_all_when_under_limit():
    content = "短文本" * 10  # 30 字符
    hits = [_hit(content)]
    kept, used = _truncate_by_chars(hits, 100)
    assert len(kept) == 1
    assert used == 30
    assert kept[0]["content"] == content


def test_truncate_stops_when_total_reaches_limit():
    hits = [_hit("A" * 100), _hit("B" * 100), _hit("C" * 100)]
    kept, used = _truncate_by_chars(hits, 250)
    # 前 2 个完整 + 第 3 个的 50 字符
    assert len(kept) == 3
    assert used == 250
    # 最后一条被截断
    assert kept[-1]["content"].endswith("(已截断)")


def test_truncate_drops_remaining_when_no_room():
    hits = [_hit("A" * 100), _hit("B" * 100)]
    kept, used = _truncate_by_chars(hits, 100)
    # 第 2 条连 1 字符都放不下 → 立即停
    assert len(kept) == 1
    assert used == 100


def test_truncate_first_hit_too_long_is_clipped_to_max():
    """第 1 条本身就比 max_chars 大:截断到 max_chars,标 (已截断)"""
    hits = [_hit("A" * 1000)]
    kept, used = _truncate_by_chars(hits, 200)
    assert len(kept) == 1
    assert used == 200
    assert kept[0]["content"].endswith("(已截断)")


def test_truncate_with_zero_limit_returns_full_count():
    """max_chars=0 表示不限制,原样返回。"""
    hits = [_hit("A" * 50), _hit("B" * 50)]
    kept, used = _truncate_by_chars(hits, 0)
    assert len(kept) == 2
    assert used == 100


def test_truncate_empty_input():
    kept, used = _truncate_by_chars([], 1000)
    assert kept == []
    assert used == 0


def test_truncate_handles_empty_content():
    hits = [_hit(""), _hit("X" * 50)]
    kept, used = _truncate_by_chars(hits, 1000)
    assert len(kept) == 2
    assert used == 50
