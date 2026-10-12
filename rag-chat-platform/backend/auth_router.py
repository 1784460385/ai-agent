from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, user_payload, verify_password
from database import get_db
from models_db import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=72)


@router.post("/login")
def login(form: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username.strip()).first()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "user": user_payload(user),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


@router.post("/change-password")
def change_password(
    form: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current = db.query(User).filter(User.id == user.id).first()
    if current is None or not verify_password(form.old_password, current.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    current.password_hash = hash_password(form.new_password)
    db.commit()
    return {"status": "ok"}
