"""用 Fernet 对称加密用户的 API Key。密钥由 API_KEY_SECRET 或 JWT_SECRET 派生。"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from config import JWT_SECRET


def _fernet() -> Fernet:
    secret = os.getenv("API_KEY_SECRET") or JWT_SECRET
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("API Key 无法解密") from exc


def mask_secret(plain: str) -> str:
    text = plain.strip()
    if len(text) <= 8:
        return "****"
    if text.startswith("sk-") and len(text) > 11:
        return f"{text[:7]}********{text[-4:]}"
    return f"{text[:4]}********{text[-4:]}"
