"""safe_strings 单元测试。

覆盖:
- redact_secret 把 secret 替换成 ***
- safe_exception_message 截断 + 脱敏
- public_error 固定文案
- 安全文案对外没有任何内部异常文字字样(traceback、FileNotFoundError 等)
"""

import pytest

from safe_strings import (
    PUBLIC_ERROR_MESSAGES,
    public_error,
    redact_secret,
    safe_exception_message,
)


def test_redact_secret_replaces_known_api_key():
    secret = "sk-1234567890abcdef"
    assert redact_secret("调用出错: sk-1234567890abcdef 出问题", secret) == "调用出错: *** 出问题"


def test_redact_secret_returns_text_unchanged_when_no_secret():
    assert redact_secret("hello world", None) == "hello world"


def test_redact_secret_returns_empty_for_empty_text():
    assert redact_secret("", "sk-abc") == ""
    assert redact_secret(None, "sk-abc") == ""


def test_redact_secret_does_not_touch_unrelated_text():
    text = "无关内容"
    assert redact_secret(text, "sk-different") == "无关内容"


def test_safe_exception_message_truncates_long_exception():
    big = "x" * 1000
    msg = safe_exception_message(ValueError(big), limit=80)
    assert len(msg) <= 83  # 80 + "..."
    assert msg.endswith("...")


def test_safe_exception_message_redacts_api_key():
    api_key = "sk-leak-9999"
    msg = safe_exception_message(RuntimeError(f"call failed for {api_key}"), secret=api_key)
    assert api_key not in msg
    assert "***" in msg


def test_safe_exception_message_returns_class_name_for_empty_str():
    class _Empty(Exception):
        def __str__(self):
            return ""

    msg = safe_exception_message(_Empty(""))
    # 空字符串时回退到类名
    assert "_Empty" in msg


def test_public_error_returns_known_message():
    assert public_error("api_key_invalid") == "API Key 无效或未授权"
    assert public_error("upload_too_large") == "文件超过大小限制"


def test_public_error_falls_back_to_internal_error():
    assert "服务" in public_error("nonexistent_key")


def test_public_error_uses_explicit_default():
    assert public_error("nonexistent_key", default="自定义回退") == "自定义回退"


def test_public_messages_have_no_internal_leak_markers():
    """对外文案集不应包含会泄露内部实现的字样。"""
    forbidden = (
        "Traceback",
        "FileNotFoundError",
        "ValueError",
        "AttributeError",
        "Exception:",
        "sk-",  # 不应硬编码 API key 前缀
    )
    for key, msg in PUBLIC_ERROR_MESSAGES.items():
        for token in forbidden:
            assert token not in msg, f"PUBLIC_ERROR_MESSAGES[{key}] 包含 {token}: {msg}"
