"""摘要模型独立测试。

覆盖:
- SUMMARY_MODEL 默认值正确(deepseek-flash)
- prepare_conversation_context 用 summary_model 而非 model_name
- 默认 None 时回退到 SUMMARY_MODEL
"""

import asyncio

import pytest


def test_summary_model_default_is_flash():
    """默认摘要模型应与生成模型解耦,固定为 deepseek-flash。"""
    from config import SUMMARY_MODEL

    # 默认值
    assert SUMMARY_MODEL == "deepseek-flash"


def test_summary_model_overridable_by_env(monkeypatch):
    """通过环境变量覆盖。"""
    import importlib
    import config

    monkeypatch.setenv("SUMMARY_MODEL", "deepseek-reasoner")
    importlib.reload(config)
    assert config.SUMMARY_MODEL == "deepseek-reasoner"
    # 恢复:reload 默认值
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    importlib.reload(config)


def test_prepare_conversation_context_uses_summary_model_for_side_calls(monkeypatch):
    """验证:生成模型 = "deepseek-reasoner" 时,摘要 / 改写仍走 "deepseek-flash"。"""
    from context_memory import prepare_conversation_context
    import context_memory as cm_module

    captured = {"summary_model": None, "rewrite_model": None}

    async def fake_summarize(api_key, base_url, model, summary, pending):
        captured["summary_model"] = model
        return "新摘要"

    async def fake_rewrite(api_key, base_url, model, question, summary, recent):
        captured["rewrite_model"] = model
        return question

    monkeypatch.setattr(cm_module, "_summarize", fake_summarize)
    monkeypatch.setattr(cm_module, "_rewrite_query", fake_rewrite)

    from models_db import ChatHistory

    rows = [
        ChatHistory(id=i, user_id=1, question="问题" * 50, answer="回答" * 50, created_at=None)
        for i in range(1, 5)
    ]

    def fake_load_state(uid, cid):
        return rows, "", 0

    monkeypatch.setattr(cm_module, "_load_state", fake_load_state)

    # 不传 summary_model,应走 SUMMARY_MODEL 默认
    ctx = asyncio.run(
        prepare_conversation_context(
            user_id=1,
            conversation_id=1,
            current_question="继续",
            api_key="sk-test",
            base_url="https://x",
            model_name="deepseek-reasoner",
        )
    )
    assert captured["summary_model"] == "deepseek-flash"
    assert captured["rewrite_model"] == "deepseek-flash"
    assert isinstance(ctx, dict)


def test_prepare_conversation_context_accepts_explicit_summary_model(monkeypatch):
    """传 summary_model 时,优先用传入值。"""
    from context_memory import prepare_conversation_context
    import context_memory as cm_module

    captured = {"summary_model": None}

    async def fake_summarize(api_key, base_url, model, summary, pending):
        captured["summary_model"] = model
        return "新摘要"

    async def fake_rewrite(api_key, base_url, model, question, summary, recent):
        return question

    monkeypatch.setattr(cm_module, "_summarize", fake_summarize)
    monkeypatch.setattr(cm_module, "_rewrite_query", fake_rewrite)

    from models_db import ChatHistory

    rows = [
        ChatHistory(id=i, user_id=1, question="问题" * 50, answer="回答" * 50, created_at=None)
        for i in range(1, 5)
    ]

    def fake_load_state(uid, cid):
        return rows, "", 0

    monkeypatch.setattr(cm_module, "_load_state", fake_load_state)

    asyncio.run(
        prepare_conversation_context(
            user_id=1,
            conversation_id=1,
            current_question="继续",
            api_key="sk-test",
            base_url="https://x",
            model_name="deepseek-reasoner",
            summary_model="custom-summary-model",
        )
    )
    assert captured["summary_model"] == "custom-summary-model"
