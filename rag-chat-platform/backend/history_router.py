import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user
from database import SessionLocal, get_db
from models_db import ChatHistory, User

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
) -> None:
    db = SessionLocal()
    try:
        db.add(
            ChatHistory(
                user_id=user_id,
                question=question,
                answer=answer,
                citations=json.dumps(citations, ensure_ascii=False),
                router_departments=json.dumps(departments, ensure_ascii=False),
            )
        )
        db.commit()
    finally:
        db.close()


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
