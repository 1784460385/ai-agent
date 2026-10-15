"""对外文案与脱敏工具集中点。

约束:
- *所有*经过 HTTPException / SSE 事件 / 日志返回前端的文案必须先经过这里
- API Key 等机密字段必须先用 redact_secret() 处理(用于落库/日志)
- 不对外抛内部异常文字(异常信息只能进 log.exception(),不准进 HTTPException detail)

新增一种文案时:
1. 在 PUBLIC_ERROR_MESSAGES 加键值对
2. 后端代码 PUBLIC_ERROR_MESSAGES["xxx"] 引用
3. 前端不再硬编码中文文案,改为 PUBLIC_ERROR_MESSAGES 中一致的 key
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# 对外固定文案。前端可按 key 调用,后端必通过这里取。
PUBLIC_ERROR_MESSAGES: dict[str, str] = {
    # 鉴权
    "api_key_invalid": "API Key 无效或未授权",
    "auth_invalid_credentials": "无效的登录凭证",
    "auth_session_expired": "登录已过期,请重新登录",
    # 上游模型
    "model_upstream": "模型服务暂时不可用,请稍后再试",
    "model_rate_limited": "请求过于频繁,请稍后再试",
    "model_no_output": "没有收到模型输出,请稍后再试",
    # 检索 / 知识库
    "retrieval_failed": "知识库检索失败,请稍后再试",
    "conversation_missing": "对话不存在",
    # 上传 / 解析
    "upload_too_large": "文件超过大小限制",
    "upload_unsupported_format": "不支持的文件格式",
    "upload_malicious_filename": "无效文件名",
    "upload_payload_mismatch": "文件内容与扩展名不符",
    "upload_empty": "文件为空",
    # 输入
    "input_too_long": "问题超过 4000 字",
    "input_missing": "请输入问题或添加附件",
    "input_image_no_vision_model": "当前模型不能识别图片，请改为 deepseek-flash",
    # 限速
    "rate_limited": "请求过于频繁,请稍后再试",
    # 系统
    "internal_error": "服务暂时不可用,请稍后再试",
}


def public_error(key: str, default: str | None = None) -> str:
    """取对外文案;找不到时回退到 default(再不行用通用 internal_error)。"""
    return PUBLIC_ERROR_MESSAGES.get(key, default or PUBLIC_ERROR_MESSAGES["internal_error"])


def redact_secret(text: str | None, secret: str | None) -> str:
    """把可能出现在文本里的 API Key 替换成 ***。

    用法:
        # 把用户输入清洗后落库
        db_text = redact_secret(user_input, api_key)
    """
    if not text:
        return ""
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def safe_exception_message(exc: Exception, *, secret: str | None = None, limit: int = 300) -> str:
    """生成仅入日志的安全异常文案。

    - 去掉 secret(API Key 等)
    - 截断到 limit 字符
    - 不返回原始堆栈

    注意:这个函数的返回值 *永远不要* 直接发给前端,只能进 log.exception() 或 log.error()。
    """
    text = str(exc) or exc.__class__.__name__
    if secret:
        text = text.replace(secret, "***")
    if len(text) > limit:
        text = text[:limit] + "..."
    return text
