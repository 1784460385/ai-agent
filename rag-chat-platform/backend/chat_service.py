"""聊天业务编排。

把 chat_endpoint 的核心逻辑从 FastAPI 路由层剥离出来,纯函数 / 异步生成器,
便于单元测试和复用。Web 关注点(路由定义、StreamingResponse 头)在 chat_router.py。

输入(用户提交)
  ↓
prepare_chat_request(...) → ChatPreparation(上下文+检索结果+拼好的 messages)
  ↓
prep.stream(client) → 异步生成器,逐个产出 SSE 事件 dict
  ↓
prep.persist(...) → 把对话/回答/引用/附件落库
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Sequence

from fastapi import HTTPException

from chat_attachments import (
    AttachmentError,
    compose_user_text,
    prepare_attachments,
    vision_model,
)
from config import DEFAULT_MODEL, DEEPSEEK_BASE_URL, RETRIEVAL_TOP_K
from context_memory import prepare_conversation_context
from events import (
    EVENT_CONVERSATION,
    EVENT_DELTA,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_ROUTER,
    EVENT_SOURCES,
    ROUTER_VIA_LLM,
)
from folders import get_folder
from history_router import open_conversation, save_chat_history
from openai import APIStatusError, AsyncOpenAI, AuthenticationError
from rag_engine import build_rag_prompt
from safe_strings import PUBLIC_ERROR_MESSAGES, redact_secret
from vector_store import search_departments

log = logging.getLogger(__name__)


# ---- 中间结果 ----
@dataclass
class RouterHit:
    key: str
    name: str


@dataclass
class SourceHit:
    index: int
    source: str
    department: str
    department_name: str
    preview: str
    excerpt: str


@dataclass
class ChatContext:
    """请求准备阶段产出的所有数据,够 stream / persist 共用。"""

    user_id: int
    api_key_id: int
    api_key: str
    base_url: str
    model_name: str
    question: str  # 用户原始问题(已去前后空白)
    stored_question: str  # 落库时用的题目(无消息时用占位)
    user_text: str | None  # 拼到 user content 的文本(question + 附件文本)
    has_images: bool
    attachment_records: list  # 落库用
    history: list  # 给主模型的 history messages
    retrieval_query: str
    target_departments: list[str]
    router_via: str
    hits: list[dict]
    conversation: dict | None = None  # 流式开始时 open_conversation 拿到的
    conversation_id: int | None = None  # 用户传进来的


@dataclass
class PreparedChat:
    """chat_service 完整产出。"""

    context: ChatContext
    sources: list[SourceHit]
    router: list[RouterHit]
    system_prompt: str
    user_content: str | list  # 给主模型的 user message content(可能含 image_url)
    timings: dict[str, float] = field(default_factory=dict)


# ---- 入口 ----
async def prepare_chat_request(
    *,
    user_id: int,
    api_key_id: int,
    api_key: str,
    base_url: str,
    model_name: str,
    message: str,
    files_payload: Sequence[tuple[str, bytes]],
    conversation_id: int | None,
) -> PreparedChat:
    """解析请求参数 + 准备上下文 + 检索,产出供 stream 使用的 PreparedChat。"""
    question = message.strip()
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="问题超过 4000 字")

    if not question and not files_payload:
        raise HTTPException(status_code=400, detail="请输入问题或添加附件")

    try:
        prepared = await _to_thread(prepare_attachments, list(files_payload))
    except AttachmentError as exc:
        # AttachmentError 是附件校验/解析错误,文案可读(由我们抛出),可以直接显示
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if prepared["images"] and not vision_model(model_name):
        raise HTTPException(
            status_code=400,
            detail="当前模型不能识别图片，请改为 deepseek-flash",
        )

    user_text = compose_user_text(question, prepared["document_text"])
    stored_question = question or "请根据附件回答"

    # 续聊合法性校验
    if conversation_id is not None:
        try:
            open_conversation(user_id, conversation_id, stored_question)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="对话不存在") from exc

    # 上下文摘要 + 检索 query 改写
    started = time.perf_counter()
    # 摘要 / 改写 走 SUMMARY_MODEL(独立于生成模型,避免 reasoner 类慢模型拖累)
    from config import SUMMARY_MODEL as DEFAULT_SUMMARY_MODEL

    context = await prepare_conversation_context(
        user_id,
        conversation_id,
        user_text or stored_question,
        api_key,
        base_url,
        model_name,
        summary_model=DEFAULT_SUMMARY_MODEL,
    )
    history = context["messages"]
    retrieval_query = context["retrieval_query"] or (question or stored_question)
    t_context = time.perf_counter()

    # 路由(已经在 context_memory 的 prepare 里走过,
    #  这里其实重复了一次——但 chat_service 的入口语义是"再路由一次",保持不变)
    from router import route_query  # 延迟导入避免循环

    target_departments, via = await route_query(
        query=retrieval_query,
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        user_id=user_id,
    )
    t_route = time.perf_counter()

    # 检索(向量 + 关键词)
    try:
        hits = await _to_thread(
            search_departments,
            user_id,
            target_departments,
            retrieval_query,
            RETRIEVAL_TOP_K,
            [question],
        )
    except Exception as exc:  # noqa: BLE001
        # 安全:对外只给固定文案,详细堆栈进日志
        log.exception("检索失败 user=%s query=%r", user_id, retrieval_query)
        raise HTTPException(status_code=500, detail=PUBLIC_ERROR_MESSAGES["retrieval_failed"]) from exc
    t_search = time.perf_counter()

    # 组装 system prompt 与 sources
    labeled_docs = [f"[来源: {hit['source']}]\n{hit['content']}" for hit in hits]
    system_prompt = build_rag_prompt(stored_question, labeled_docs)
    sources = [
        SourceHit(
            index=i,
            source=hit["source"],
            department=hit["department"],
            department_name=hit["department_name"],
            preview=" ".join(hit["content"].split())[:80],
            excerpt=hit["content"],
        )
        for i, hit in enumerate(hits, start=1)
    ]
    router = [
        RouterHit(
            key=d,
            name=(get_folder(user_id, d) or {}).get("name", d),
        )
        for d in target_departments
    ]

    # user content(可能含 image_url)
    if prepared["images"]:
        user_content: str | list = [{"type": "text", "text": user_text}]
        user_content.extend(
            {
                "type": "image_url",
                "image_url": {"url": image["data_url"], "detail": "high"},
            }
            for image in prepared["images"]
        )
    else:
        user_content = user_text

    ctx = ChatContext(
        user_id=user_id,
        api_key_id=api_key_id,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        question=question,
        stored_question=stored_question,
        user_text=user_text,
        has_images=bool(prepared["images"]),
        attachment_records=prepared.get("records", []),
        history=history,
        retrieval_query=retrieval_query,
        target_departments=target_departments,
        router_via=via,
        hits=hits,
        conversation_id=conversation_id,
    )
    timings = {
        "context": t_context - started,
        "route": t_route - t_context,
        "search": t_search - t_route,
        "total_prepare": t_search - started,
    }
    return PreparedChat(
        context=ctx,
        sources=sources,
        router=router,
        system_prompt=system_prompt,
        user_content=user_content,
        timings=timings,
    )


# ---- 流式生成 ----
async def stream_chat(prepared: PreparedChat) -> AsyncIterator[dict]:
    """异步生成器,逐个产出 SSE 事件 dict。Web 层负责 JSON 编码 + 帧头。

    事件流:
      {type: conversation, id, title}
      {type: router, via, departments:[{key,name}]}
      {type: sources, sources:[...]}
      {type: delta, content}            × N
      {type: done}                       | 或 {type: error, message}
    """
    ctx = prepared.context

    # 续聊开口或新建对话
    try:
        conversation = open_conversation(
            ctx.user_id,
            ctx.conversation_id,
            redact_secret(ctx.stored_question, ctx.api_key),
        )
    except LookupError:
        yield {"type": EVENT_ERROR, "message": PUBLIC_ERROR_MESSAGES["conversation_missing"]}
        return
    ctx.conversation = conversation

    yield {
        "type": EVENT_CONVERSATION,
        "id": conversation["id"],
        "title": conversation["title"],
    }
    yield {
        "type": EVENT_ROUTER,
        "via": ctx.router_via,
        "departments": [{"key": r.key, "name": r.name} for r in prepared.router],
    }
    if prepared.sources:
        yield {
            "type": EVENT_SOURCES,
            "sources": [s.__dict__ for s in prepared.sources],
        }

    client = AsyncOpenAI(
        api_key=ctx.api_key,
        base_url=ctx.base_url or DEEPSEEK_BASE_URL,
        max_retries=0,
        timeout=90,
    )
    try:
        llm_stream = await client.chat.completions.create(
            model=ctx.model_name or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": prepared.system_prompt},
                *ctx.history,
                {"role": "user", "content": prepared.user_content},
            ],
            stream=True,
            temperature=0.3,
        )
    except AuthenticationError:
        yield {"type": EVENT_ERROR, "message": PUBLIC_ERROR_MESSAGES["api_key_invalid"]}
        return
    except APIStatusError as exc:
        if exc.status_code == 401:
            yield {"type": EVENT_ERROR, "message": PUBLIC_ERROR_MESSAGES["api_key_invalid"]}
            return
        log.exception("模型服务返回错误 status=%s", exc.status_code)
        yield {"type": EVENT_ERROR, "message": PUBLIC_ERROR_MESSAGES["model_upstream"]}
        return
    except Exception:  # noqa: BLE001
        log.exception("模型服务不可用")
        yield {"type": EVENT_ERROR, "message": PUBLIC_ERROR_MESSAGES["model_upstream"]}
        return

    async for raw_event in _iter_stream_events(llm_stream):
        yield raw_event


async def _iter_stream_events(llm_stream) -> AsyncIterator[dict]:
    """包装 OpenAI 流,产出 SSE 事件 dict。出错时返回 error 事件。"""
    parts: list[str] = []
    error_message: str | None = None
    try:
        async for chunk in llm_stream:
            if not chunk.choices:
                continue
            content = getattr(chunk.choices[0].delta, "content", None)
            if content:
                parts.append(content)
                yield {"type": EVENT_DELTA, "content": content}
    except AuthenticationError:
        error_message = PUBLIC_ERROR_MESSAGES["api_key_invalid"]
    except Exception:  # noqa: BLE001
        log.exception("流式生成异常")
        error_message = PUBLIC_ERROR_MESSAGES["model_upstream"]

    if error_message:
        yield {"type": EVENT_ERROR, "message": error_message}
    else:
        yield {"type": EVENT_DONE}


# ---- 落库 ----
def persist_chat(prepared: PreparedChat, content: str) -> None:
    """把对话结果写库。失败仅记日志,不抛(用户已经看到回答)。"""
    ctx = prepared.context
    if ctx.conversation is None:
        return
    citations = [
        {"file": hit.get("source") or "未知来源", "snippet": str(hit.get("content") or "")[:800]}
        for hit in ctx.hits
        if hit.get("content")
    ]
    try:
        save_chat_history(
            ctx.user_id,
            redact_secret(ctx.stored_question, ctx.api_key),
            redact_secret(content, ctx.api_key),
            citations,
            [r.name for r in prepared.router],
            ctx.conversation["id"],
            ctx.attachment_records,
        )
    except Exception:  # noqa: BLE001
        log.exception("落库失败 user=%s conv=%s", ctx.user_id, ctx.conversation["id"])


# ---- 工具 ----
async def _to_thread(func, *args, **kwargs):
    """统一异步→线程池出口,便于将来换实现。"""
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)


# ---- 给上层包 SSE 帧 ----
def sse_payload(payload: dict) -> str:
    """编码单个事件为 SSE 帧(含 data: 前缀与双换行)。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def make_event_stream(prepared: PreparedChat) -> AsyncIterator[str]:
    """把 stream_chat + persist_chat 组合,生成可直接喂给 StreamingResponse 的字符串。

    persist 在 done/error 触发后跑,把已拼好的 content 落库。
    """
    return _persist_after_stream(prepared)


async def _persist_after_stream(prepared: PreparedChat) -> AsyncIterator[str]:
    parts: list[str] = []
    saw_error = False
    finished_cleanly = False
    async for event in stream_chat(prepared):
        if event.get("type") == EVENT_DELTA and event.get("content"):
            parts.append(event["content"])
        if event.get("type") == EVENT_DONE:
            finished_cleanly = True
        if event.get("type") == EVENT_ERROR:
            saw_error = True
        yield sse_payload(event)

    if saw_error:
        # 流式发生错误:拼接已收到的内容 + 错误信息(供前端兜底显示)
        content = "".join(parts)
        if content:
            content = f"{content}\n\n{_last_error_text(prepared)}"
        else:
            content = _last_error_text(prepared) or "生成失败"
    elif finished_cleanly and not parts:
        content = "没有收到模型输出"
    elif not finished_cleanly:
        # 客户端中断等情况:仍然落库(记录已生成的部分)
        content = "".join(parts) or "已停止生成"
    else:
        content = "".join(parts)

    persist_chat(prepared, content)


def _last_error_text(prepared: PreparedChat) -> str:
    """从 stream_chat 里提取最后一次 error 文案(用于落库时的 content)。"""
    # 由于 stream_chat 是异步生成器,我们已经从事件里知道 saw_error,
    # 这里只给一个保底文案。具体文案已经通过 SSE 事件告知前端。
    return "生成过程中出错"