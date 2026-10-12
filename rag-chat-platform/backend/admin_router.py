from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import hash_password, require_admin
from database import get_db, list_folders
from models_db import User
from vector_store import delete_collection_by_name

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=72)


def _iso(value) -> str:
    text = value.isoformat() if value is not None else ""
    if text and not text.endswith("Z") and "+" not in text:
        return text + "Z"
    return text


def _user_item(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": _iso(user.created_at),
    }


@router.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(User).order_by(User.id.asc())
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": [_user_item(row) for row in rows]}


@router.post("/users", status_code=201)
def create_user(form: CreateUserRequest, db: Session = Depends(get_db)):
    username = form.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=username, password_hash=hash_password(form.password), role=form.role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_item(user)


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    form: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and form.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账号")
    if form.role is not None:
        user.role = form.role
    if form.is_active is not None:
        user.is_active = form.is_active
    if form.password:
        user.password_hash = hash_password(form.password)
    db.commit()
    db.refresh(user)
    return _user_item(user)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    for folder in list_folders(user_id):
        delete_collection_by_name(folder["collection"])
    db.delete(user)
    db.commit()
    return {"status": "ok", "id": user_id}
