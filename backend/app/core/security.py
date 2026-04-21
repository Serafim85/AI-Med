"""Password hashing, JWT issuing/decoding and the FastAPI auth dependency."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 12

# bcrypt ограничен 72 байтами пароля. Мы преобразуем в UTF-8 и обрезаем
# на безопасной границе — это стандартная практика (то же делает, например,
# Django). Хэши, созданные этой функцией, читаются стандартным
# `bcrypt.checkpw`, в том числе старыми реализациями passlib.
_BCRYPT_MAX_BYTES = 72


def _prepare(plain: str) -> bytes:
    data = plain.encode("utf-8")
    if len(data) <= _BCRYPT_MAX_BYTES:
        return data
    # Обрезаем по байтам, не ломая последнюю multibyte-последовательность.
    truncated = data[:_BCRYPT_MAX_BYTES]
    while truncated:
        try:
            truncated.decode("utf-8")
            break
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return truncated


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_prepare(plain), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prepare(plain), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    subject: str | uuid.UUID,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    exp = now + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])


_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Неверные учётные данные",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise _CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise _CREDENTIALS_EXCEPTION from None

    subject = payload.get("sub")
    if not subject:
        raise _CREDENTIALS_EXCEPTION

    try:
        user_id = uuid.UUID(str(subject))
    except (TypeError, ValueError):
        raise _CREDENTIALS_EXCEPTION from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user
