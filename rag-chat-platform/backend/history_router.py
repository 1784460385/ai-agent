import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user
from database import SessionLocal, get_db
from db_lock import db_session
from models_db import ChatHistory, Conversation, User, utcnow

router = APIRouter(prefix="/api/history", tags=["history"])


def _iso(value) -> str:
    text = value.isoformat() if value is not None else ""
    if text and not text.endswith("Z") and "+" not in text:
        return text + "Z"
    return text


def _loads(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


def _item(row: ChatHistory, with_answer: bool) -> dict:
    payload = {
        "id": row.id,
        "question": row.question,
        "router_departments": _loads(row.router_departments, []),
        "created_at": _iso(row.created_at),
    }
    if with_answer:
        payload["answer"] = row.answer
        payload["citations"] = _loads(row.citations, [])
    return payload


def save_chat_history(
    user_id: int,
    question: str,
    answer: str,
    citations: list,
    departments: list[str],
    conversation_id: int,
    attachments: list | None = None,
) -> None:
    """落库对话 + 更新 Conversation.updated_at。异常向上抛以便上层日志。"""
    with db_session() as db:
        db.add(
            ChatHistory(
                user_id=user_id,
                question=question,
                answer=answer,
                citations=json.dumps(citations, ensure_ascii=False),
                router_departments=json.dumps(departments, ensure_ascii=False),
                conversation_id=conversation_id,
                attachments=json.dumps(attachments or [], ensure_ascii=False),
            )
        )
        thread = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if thread is not None:
            thread.updated_at = utcnow()


def open_conversation(user_id: int, conversation_id: int | None, question: str) -> dict:
    """开新对话 / 续聊开口。失败时抛 LookupError 或 IntegrityError 让上游处理。"""
    with db_session() as db:
        if conversation_id is not None:
            thread = (
                db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
                .first()
            )
            if thread is None:
                raise LookupError
            return {"id": thread.id, "title": thread.title}
        title = " ".join(question.split())[:32] or "新对话"
        thread = Conversation(user_id=user_id, title=title)
        db.add(thread)
        db.flush()
        db.refresh(thread)
        return {"id": thread.id, "title": thread.title, "updated_at": _iso(thread.updated_at)}


def backfill_conversations() -> None:
    with db_session() as db:
        rows = db.query(ChatHistory).filter(ChatHistory.conversation_id.is_(None)).all()
        for row in rows:
            title = " ".join((row.question or "").split())[:32] or "新对话"
            thread = Conversation(
                user_id=row.user_id,
                title=title,
                created_at=row.created_at,
                updated_at=row.created_at,
            )
            db.add(thread)
            db.flush()
            row.conversation_id = thread.id


def _thread_item(thread: Conversation) -> dict:
    return {"id": thread.id, "title": thread.title, "updated_at": _iso(thread.updated_at)}


def prior_messages(user_id: int, conversation_id: int | None) -> list[dict]:
    """加载最近 N 轮历史,组装成 OpenAI messages 格式。读路径,只读事务。"""
    if conversation_id is None:
        return []
    with db_session() as db:
        rows = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.conversation_id == conversation_id)
            .order_by(ChatHistory.id.desc())
            .limit(6)
            .all()
        )
    messages = []
    for row in reversed(rows):
        text = row.question or ""
        attached = _loads(row.attachments, [])
        if isinstance(attached, list) and attached:
            lines = [f"{item.get('name')}：{item.get('summary') or ''}" for item in attached if isinstance(item, dict)]
            text = (text + "\n\n附件摘要\n" + "\n".join(lines)).strip()
        messages.append({"role": "user", "content": text or "（附件）"})
        messages.append({"role": "assistant", "content": row.answer or ""})
    return messages


def _messages(rows: list[ChatHistory]) -> list[dict]:
    messages = []
    for row in rows:
        user_message: dict = {"role": "user", "content": row.question}
        attached = _loads(row.attachments, [])
        if isinstance(attached, list) and attached:
            user_message["attachments"] = [
                {"name": item.get("name") or "附件", "kind": item.get("kind") or "file"}
                for item in attached
                if isinstance(item, dict)
            ]
        messages.append(user_message)
        citations = _loads(row.citations, [])
        departments = _loads(row.router_departments, [])
        assistant: dict = {"role": "assistant", "content": row.answer}
        if isinstance(citations, list) and citations:
            assistant["sources"] = [
                {
                    "index": index,
                    "source": item.get("file") or "未知来源",
                    "preview": " ".join(str(item.get("snippet") or "").split())[:80],
                    "excerpt": item.get("snippet") or "",
                }
                for index, item in enumerate(citations, start=1)
                if isinstance(item, dict)
            ]
        if isinstance(departments, list) and departments:
            assistant["router"] = {
                "via": "rule",
                "departments": [
                    {"key": name, "name": name} if isinstance(name, str) else name
                    for name in departments
                ],
            }
        messages.append(assistant)
    return messages


threads = APIRouter(prefix="/api/conversations", tags=["conversations"])


@threads.get("")
def list_threads(
    keyword: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation).filter(Conversation.user_id == user.id)
    if keyword and keyword.strip():
        escaped = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(Conversation.title.like(f"%{escaped}%", escape="\\"))
    rows = query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(200).all()
    return {"items": [_thread_item(row) for row in rows]}


@threads.get("/{thread_id}")
def get_thread(thread_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(Conversation).filter(Conversation.id == thread_id, Conversation.user_id == user.id).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    rows = (
        db.query(ChatHistory)
        .filter(ChatHistory.conversation_id == thread.id, ChatHistory.user_id == user.id)
        .order_by(ChatHistory.id.asc())
        .all()
    )
    return {**_thread_item(thread), "messages": _messages(rows)}


@threads.delete("/{thread_id}")
def delete_thread(thread_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(Conversation).filter(Conversation.id == thread_id, Conversation.user_id == user.id).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(ChatHistory).filter(ChatHistory.conversation_id == thread.id, ChatHistory.user_id == user.id).delete()
    db.delete(thread)
    db.commit()
    return {"status": "ok", "id": thread_id}


@router.get("")
def list_history(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ChatHistory).filter(ChatHistory.user_id == user.id)
    if keyword and keyword.strip():
        escaped = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(ChatHistory.question.like(f"%{escaped}%", escape="\\"))
    total = query.count()
    rows = (
        query.order_by(ChatHistory.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_item(row, with_answer=True) for row in rows],
    }


@router.get("/{history_id}")
def get_history(history_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(ChatHistory).filter(ChatHistory.id == history_id, ChatHistory.user_id == user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return _item(row, with_answer=True)


@router.delete("/{history_id}")
def delete_history(history_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(ChatHistory).filter(ChatHistory.id == history_id, ChatHistory.user_id == user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return {"status": "ok", "id": history_id}


@router.delete("")
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(ChatHistory).filter(ChatHistory.user_id == user.id).delete()
    db.commit()
    return {"status": "ok"}
