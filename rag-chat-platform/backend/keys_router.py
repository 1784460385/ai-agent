from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from config import DEEPSEEK_BASE_URL, DEFAULT_MODEL
from database import get_db
from models_db import User, UserApiKey
from secret_box import decrypt_secret, encrypt_secret, mask_secret

router = APIRouter(prefix="/api/keys", tags=["api-keys"])

MODELS = {"deepseek-flash", "deepseek-chat", "deepseek-reasoner"}


class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    api_key: str = Field(..., min_length=8, max_length=200)
    model: str = Field(default=DEFAULT_MODEL, max_length=80)
    base_url: str = Field(default=DEEPSEEK_BASE_URL, max_length=200)


class KeyUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    api_key: str = Field(default="", max_length=200)
    model: str = Field(default=DEFAULT_MODEL, max_length=80)
    base_url: str = Field(default=DEEPSEEK_BASE_URL, max_length=200)


def _check(model: str, base_url: str, api_key: str | None) -> None:
    if model not in MODELS:
        raise HTTPException(status_code=400, detail="不支持的模型")
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Base URL 需要以 http:// 或 https:// 开头")
    if api_key is not None and not api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="API Key 应以 sk- 开头")


def _public(row: UserApiKey) -> dict:
    try:
        masked = mask_secret(decrypt_secret(row.api_key_encrypted))
    except ValueError:
        masked = "****"
    return {
        "id": row.id,
        "name": row.name,
        "masked_key": masked,
        "model": row.model,
        "base_url": row.base_url,
        "is_default": bool(row.is_default),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _owned(db: Session, user_id: int, key_id: int) -> UserApiKey:
    row = db.query(UserApiKey).filter(UserApiKey.id == key_id, UserApiKey.user_id == user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return row


def _clear_default(db: Session, user_id: int) -> None:
    db.query(UserApiKey).filter(UserApiKey.user_id == user_id, UserApiKey.is_default.is_(True)).update(
        {"is_default": False}
    )


def resolve_api_key(user_id: int, key_id: int) -> tuple[str, str, str]:
    """返回当前用户自己的明文 Key、模型、Base URL。调用方用完不要写入日志。"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(UserApiKey).filter(UserApiKey.id == key_id, UserApiKey.user_id == user_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="请先在模型配置里选择自己的 API Key")
        try:
            plain = decrypt_secret(row.api_key_encrypted)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="API Key 无法解密，请重新保存") from exc
        return plain, row.model, row.base_url
    finally:
        db.close()


@router.get("")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(UserApiKey)
        .filter(UserApiKey.user_id == user.id)
        .order_by(UserApiKey.is_default.desc(), UserApiKey.id.asc())
        .all()
    )
    return {"items": [_public(row) for row in rows]}


@router.post("")
def create_key(payload: KeyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.name.strip()
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip() or DEEPSEEK_BASE_URL
    _check(payload.model, base_url, api_key)
    exists = db.query(UserApiKey.id).filter(UserApiKey.user_id == user.id).first()
    row = UserApiKey(
        user_id=user.id,
        name=name,
        api_key_encrypted=encrypt_secret(api_key),
        model=payload.model,
        base_url=base_url,
        is_default=exists is None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _public(row)


@router.put("/{key_id}")
def update_key(key_id: int, payload: KeyUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _owned(db, user.id, key_id)
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip() or DEEPSEEK_BASE_URL
    _check(payload.model, base_url, api_key or None)
    row.name = payload.name.strip()
    row.model = payload.model
    row.base_url = base_url
    if api_key:
        row.api_key_encrypted = encrypt_secret(api_key)
    db.commit()
    db.refresh(row)
    return _public(row)


@router.delete("/{key_id}")
def delete_key(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _owned(db, user.id, key_id)
    was_default = row.is_default
    db.delete(row)
    db.flush()
    if was_default:
        nxt = db.query(UserApiKey).filter(UserApiKey.user_id == user.id).order_by(UserApiKey.id.asc()).first()
        if nxt is not None:
            nxt.is_default = True
    db.commit()
    return {"status": "ok", "id": key_id}


@router.post("/{key_id}/default")
def set_default(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _owned(db, user.id, key_id)
    _clear_default(db, user.id)
    row.is_default = True
    db.commit()
    db.refresh(row)
    return _public(row)
