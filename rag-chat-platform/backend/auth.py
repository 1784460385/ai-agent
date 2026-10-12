import bcrypt
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from database import SessionLocal
from models_db import User

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("About", (), {"__version__": getattr(bcrypt, "__version__", "4")})()

_bcrypt_hashpw = bcrypt.hashpw


def _hashpw(password, salt):
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _bcrypt_hashpw(password[:72], salt)


bcrypt.hashpw = _hashpw

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def authenticate_token(token: str) -> User:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="无效的登录凭证") from exc
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    finally:
        db.close()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return user


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="无效的登录凭证")
    return authenticate_token(token)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def ensure_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == "admin").first():
            return
        db.add(
            User(
                username="admin",
                password_hash=hash_password("Aa123456"),
                role="admin",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def user_payload(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}
