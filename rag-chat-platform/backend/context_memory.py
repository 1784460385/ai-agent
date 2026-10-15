"""同一会话的上下文：最近原文 + 增量摘要 + 检索 query 改写。

现有存储是 chat_history 一行一轮（问题 + 回答），不另建 messages 表。
summary_last_history_id 指向已纳入摘要的最后一条 chat_history.id。
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI

from config import (
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    RECENT_CONTEXT_TURNS,
    SUMMARY_MODEL,
    SUMMARY_TRIGGER_TOKENS,
    SUMMARY_TRIGGER_TURNS,
)
from db_lock import db_session
from models_db import ChatHistory, Conversation, utcnow

_log = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是对话摘要器。请把“已有摘要”和“新增对话”合并成更新后的摘要。

要求：
1. 只保留对后续回答有用的信息。
2. 重点保留：用户目标、背景、约束、偏好、已确认事实、未解决问题、重要实体、数字、时间、代码、ID。
3. 不要编造，不要加入对话中不存在的信息。
4. 如果新信息与旧摘要冲突，以新对话为准。
5. 删除寒暄、重复、无关内容。
6. 用简洁要点输出，不超过 600 个词。

已有摘要：
{old_summary}

新增对话：
{new_messages}

更新后的摘要："""

REWRITE_PROMPT = """你是检索查询改写器。用户的新问题可能包含“它、这个、第二个、上述”等指代。
请结合历史摘要和最近对话，改写成一条可独立用于知识库检索的查询。

要求：
1. 只输出改写后的查询，不要解释。
2. 保留关键实体、产品名、报错、配置项。
3. 如果当前问题已经完整，原样输出即可。
4. 不超过 200 字。

历史摘要：
{summary}

最近用户问题：
{recent}

当前问题：
{question}"""

_summary_locks: dict[int, asyncio.Lock] = {}


def estimate_tokens(text: str) -> int:
    """中英混合的粗估：约 2 个字符 1 个 token，只用于决定是否触发摘要。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return max(1, len(cleaned) // 2)


def _loads(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


def turn_user_text(row: ChatHistory) -> str:
    text = row.question or ""
    attached = _loads(row.attachments, [])
    if isinstance(attached, list) and attached:
        lines = [
            f"{item.get('name')}：{item.get('summary') or ''}"
            for item in attached
            if isinstance(item, dict)
        ]
        text = (text + "\n\n附件摘要\n" + "\n".join(lines)).strip()
    return text or "（附件）"


def turn_tokens(row: ChatHistory) -> int:
    return estimate_tokens(turn_user_text(row)) + estimate_tokens(row.answer or "")


def split_turns(rows: list[ChatHistory], summary_last_id: int) -> tuple[list[ChatHistory], list[ChatHistory]]:
    """返回 (待摘要轮次, 最近原文轮次)。当前问题尚未入库，不在 rows 里。"""
    recent = rows[-RECENT_CONTEXT_TURNS:] if rows else []
    older = rows[:-RECENT_CONTEXT_TURNS] if len(rows) > RECENT_CONTEXT_TURNS else []
    pending = [row for row in older if row.id > (summary_last_id or 0)]
    return pending, recent


def _lock_for(conversation_id: int) -> asyncio.Lock:
    lock = _summary_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _summary_locks[conversation_id] = lock
    return lock


def _load_state(user_id: int, conversation_id: int) -> tuple[list[ChatHistory], str, int]:
    """同步读路径(由 asyncio.to_thread 包装)。返回摘要 + 增量 chat_history 行。"""
    with db_session() as db:
        thread = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if thread is None:
            return [], "", 0
        rows = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == conversation_id)
            .order_by(ChatHistory.id.asc())
            .all()
        )
        # 在 session 关闭前把所有字段拷贝到本地,避免延迟属性访问跨 session 报错
        result: list[ChatHistory] = []
        for row in rows:
            detached = ChatHistory(
                id=row.id,
                user_id=row.user_id,
                question=row.question,
                answer=row.answer,
                router_departments=row.router_departments,
                citations=row.citations,
                attachments=row.attachments,
                conversation_id=row.conversation_id,
                created_at=row.created_at,
            )
            result.append(detached)
        summary = thread.summary or ""
        last_id = int(thread.summary_last_history_id or 0)
        return result, summary, last_id


def _save_summary(user_id: int, conversation_id: int, summary: str, last_history_id: int) -> None:
    """落库摘要 + 维护 summary_last_history_id。"""
    with db_session() as db:
        thread = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if thread is None:
            return
        thread.summary = summary[:4000]
        thread.summary_last_history_id = last_history_id
        thread.summary_updated_at = utcnow()


def _format_turns(rows: list[ChatHistory]) -> str:
    blocks = []
    for index, row in enumerate(rows, start=1):
        blocks.append(f"第{index}轮\n用户：{turn_user_text(row)}\n助手：{row.answer or ''}")
    return "\n\n".join(blocks)


def _should_summarize(pending: list[ChatHistory]) -> bool:
    if not pending:
        return False
    tokens = sum(turn_tokens(row) for row in pending)
    return tokens >= SUMMARY_TRIGGER_TOKENS or len(pending) >= SUMMARY_TRIGGER_TURNS


def _trim_pending(pending: list[ChatHistory]) -> list[ChatHistory]:
    """摘要失败时只临时带上较新的旧原文，避免上下文无限变长。"""
    kept: list[ChatHistory] = []
    tokens = 0
    for row in reversed(pending):
        cost = turn_tokens(row)
        if kept and tokens + cost > SUMMARY_TRIGGER_TOKENS:
            break
        kept.append(row)
        tokens += cost
    kept.reverse()
    return kept


def _messages_from_turns(rows: list[ChatHistory]) -> list[dict]:
    messages = []
    for row in rows:
        messages.append({"role": "user", "content": turn_user_text(row)})
        messages.append({"role": "assistant", "content": row.answer or ""})
    return messages


def _fallback_query(question: str, recent: list[ChatHistory]) -> str:
    last_user = ""
    for row in reversed(recent):
        last_user = (row.question or "").strip()
        if last_user:
            break
    if last_user and last_user != question:
        return f"{last_user}\n{question}"[:300]
    return question


async def _complete(api_key: str, base_url: str, model: str, prompt: str, max_tokens: int) -> str:
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or DEEPSEEK_BASE_URL,
        max_retries=0,
        timeout=30,
    )
    response = await client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


async def _summarize(api_key: str, base_url: str, model: str, old_summary: str, pending: list[ChatHistory]) -> str:
    prompt = SUMMARY_PROMPT.format(
        old_summary=old_summary.strip() or "（无）",
        new_messages=_format_turns(pending),
    )
    text = await _complete(api_key, base_url, model, prompt, max_tokens=800)
    return text[:4000]


async def _rewrite_query(
    api_key: str,
    base_url: str,
    model: str,
    question: str,
    summary: str,
    recent: list[ChatHistory],
) -> str:
    recent_users = [row.question.strip() for row in recent if (row.question or "").strip()]
    prompt = REWRITE_PROMPT.format(
        summary=summary.strip() or "（无）",
        recent="\n".join(recent_users) or "（无）",
        question=question,
    )
    text = await _complete(api_key, base_url, model, prompt, max_tokens=200)
    line = " ".join(text.split())
    return (line or question)[:300]


async def prepare_conversation_context(
    user_id: int,
    conversation_id: int | None,
    current_question: str,
    api_key: str,
    base_url: str,
    model_name: str,
    summary_model: str | None = None,
) -> dict:
    """返回拼进主模型的历史消息，以及用于路由和检索的 query。

    - `model_name`:用户为生成侧选的模型(走 chat_service 调用主模型时)
    - `summary_model`:摘要 / 改写专用模型,默认 config.SUMMARY_MODEL(deepseek-flash)。
      与生成模型解耦,避免用户为生成选 `deepseek-reasoner` 时,摘要也跟着慢、跟着贵。
    """
    question = (current_question or "").strip()
    if not conversation_id:
        return {"messages": [], "retrieval_query": question}

    # 解耦:摘要 / 改写固定走 SUMMARY_MODEL,生成模型只用于主对话
    side_model = summary_model or SUMMARY_MODEL

    async def refresh() -> tuple[str, list[ChatHistory], list[ChatHistory]]:
        rows, summary, last_id = await asyncio.to_thread(_load_state, user_id, conversation_id)
        pending, recent = split_turns(rows, last_id)
        return summary, pending, recent

    summary, pending, recent = await refresh()
    if _should_summarize(pending):
        async with _lock_for(conversation_id):
            summary, pending, recent = await refresh()
            if _should_summarize(pending):
                try:
                    summary = await _summarize(api_key, base_url, side_model, summary, pending)
                    last_id = pending[-1].id
                    await asyncio.to_thread(_save_summary, user_id, conversation_id, summary, last_id)
                    pending = []
                except Exception as exc:  # noqa: BLE001
                    _log.warning("对话摘要失败: %s", exc)
                    pending = _trim_pending(pending)

    retrieval_query = question
    if summary or recent:
        try:
            retrieval_query = await _rewrite_query(api_key, base_url, side_model, question, summary, recent)
        except Exception as exc:  # noqa: BLE001
            _log.warning("检索查询改写失败: %s", exc)
            retrieval_query = _fallback_query(question, recent)

    messages: list[dict] = []
    if summary.strip():
        messages.append({"role": "system", "content": f"历史对话摘要：\n{summary.strip()}"})
    messages.extend(_messages_from_turns(pending))
    messages.extend(_messages_from_turns(recent))
    return {"messages": messages, "retrieval_query": retrieval_query or question}
