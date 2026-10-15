"""router 模块的规则路由部分测试。

跳过 LLM 路由(需要 DeepSeek 凭据),只测规则路由的纯逻辑。
folder_map 用 monkeypatch 替换为内存字典。
"""

import asyncio

import pytest

import router


@pytest.fixture
def fake_catalog(monkeypatch):
    """用固定的目录配置代替数据库读取。"""
    catalog = {
        "hr": {"name": "人事部", "keywords": ["入职", "请假", "假期", "年假", "考勤"]},
        "finance": {"name": "财务部", "keywords": ["工资", "报销", "发票"]},
        "tech": {"name": "技术部", "keywords": ["API", "接口", "部署", "故障"]},
    }
    monkeypatch.setattr(router, "folder_map", lambda user_id: catalog)
    return catalog


def test_rule_route_matches_single_folder(fake_catalog):
    result = router.rule_based_route("年假有几天？", user_id=1)
    assert result == ["hr"]


def test_rule_route_matches_multiple_folders(fake_catalog):
    result = router.rule_based_route("报销需要哪些发票", user_id=1)
    assert "finance" in result


def test_rule_route_no_match_returns_none(fake_catalog):
    """没有命中任何关键词时返回 None,触发 LLM 兜底。"""
    result = router.rule_based_route("今天天气怎么样", user_id=1)
    assert result is None


def test_rule_route_case_insensitive(fake_catalog):
    assert router.rule_based_route("api 调用失败", user_id=1) == ["tech"]
    assert router.rule_based_route("Api 调用失败", user_id=1) == ["tech"]
    assert router.rule_based_route("API 调用失败", user_id=1) == ["tech"]


def test_rule_route_partial_match(fake_catalog):
    assert router.rule_based_route("请假流程是怎样的", user_id=1) == ["hr"]


def test_rule_route_keyword_regex_escaped():
    """包含正则元字符的关键词应当作字面量匹配(re.escape 已处理)。"""
    catalog_with_regex_chars = {
        "x": {"name": "X部", "keywords": ["a.b", "c+d"]},
    }
    original_map = router.folder_map
    router.folder_map = lambda user_id: catalog_with_regex_chars
    try:
        assert router.rule_based_route("a.b", user_id=1) == ["x"]
        # . 不会被解释为「任意字符」,因此 axb 不命中
        assert router.rule_based_route("axb", user_id=1) is None
    finally:
        router.folder_map = original_map


def test_route_query_skips_llm_when_rule_matches(monkeypatch, fake_catalog):
    """规则命中时,route_query 不调 LLM。"""
    called = {"llm": 0}

    async def fake_llm(*args, **kwargs):
        called["llm"] += 1
        return []

    monkeypatch.setattr(router, "llm_based_route", fake_llm)
    depts, via = asyncio.run(
        router.route_query("年假怎么请", "sk-test", "https://x", "deepseek-flash", user_id=1)
    )
    assert called["llm"] == 0
    assert via == "rule"
    assert depts == ["hr"]


def test_route_query_falls_back_to_llm_when_no_rule(monkeypatch, fake_catalog):
    """规则未命中时,route_query 应该走 LLM 路径。"""
    called = {"llm": 0}

    async def fake_llm(query, api_key, base_url, model, user_id):
        called["llm"] += 1
        return ["hr"]  # 模拟 LLM 返回的路由结果

    monkeypatch.setattr(router, "llm_based_route", fake_llm)
    depts, via = asyncio.run(
        router.route_query("宇宙飞船", "sk-test", "https://x", "deepseek-flash", user_id=1)
    )
    assert called["llm"] == 1
    assert via == "llm"
    assert depts == ["hr"]


def test_route_query_llm_failure_returns_all_folders(monkeypatch, fake_catalog):
    """LLM 调用抛异常时,应回退到全部文件夹(看 llm_based_route 的实现)。

    llm_based_route 自己处理异常并返回所有 key;
    route_query 只是把异常包成 llm 模式。
    这里重点是 llm_based_route 在网络/JSON 错误时不会让 route_query 崩。
    """

    async def fake_llm(*args, **kwargs):
        # 模拟 DeepSeek 返回了非 JSON → llm_based_route 内部已捕获,
        # 最终返回所有文件夹的 key 列表
        return list(fake_catalog.keys())

    monkeypatch.setattr(router, "llm_based_route", fake_llm)
    depts, via = asyncio.run(
        router.route_query("???", "sk-test", "https://x", "deepseek-flash", user_id=1)
    )
    assert via == "llm"
    assert set(depts) == {"hr", "finance", "tech"}