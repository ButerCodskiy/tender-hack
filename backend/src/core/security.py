"""Утилиты безопасности, хеширования паролей и работы с токенами JWT."""

import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field

from src.core.config import settings

__all__ = [
    "InvalidTokenError",
    "TokenPayloadSchema",
    "TokenType",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]


class TokenType(StrEnum):
    """Типы JWT-токенов в системе."""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayloadSchema(BaseModel):
    """Схема полезной нагрузки JWT-токена."""

    sub: str = Field(..., description="Идентификатор пользователя")
    role: str = Field(..., description="Код роли пользователя")
    type: TokenType = Field(..., description="Назначение токена")
    iat: int = Field(..., description="Время выпуска токена")
    exp: int = Field(..., description="Время истечения срока действия токена")


def hash_password(password: str) -> str:
    """Создает безопасный криптографический хеш пароля с солью."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сверяет открытый пароль с сохраненным хешем."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    user_id: uuid.UUID | str,
    role_code: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Формирует кратковременный JWT-токен доступа."""
    now = datetime.now(settings.TIMEZONE)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = TokenPayloadSchema(
        sub=str(user_id),
        role=role_code,
        type=TokenType.ACCESS,
        iat=int(now.timestamp()),
        exp=int(expire.timestamp()),
    )
    return jwt.encode(
        payload.model_dump(),
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    user_id: uuid.UUID | str,
    role_code: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Формирует долгоживущий JWT-токен обновления."""
    now = datetime.now(settings.TIMEZONE)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = TokenPayloadSchema(
        sub=str(user_id),
        role=role_code,
        type=TokenType.REFRESH,
        iat=int(now.timestamp()),
        exp=int(expire.timestamp()),
    )
    return jwt.encode(
        payload.model_dump(),
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> TokenPayloadSchema:
    """Декодирует и валидирует JWT-токен через Pydantic-схему."""
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return TokenPayloadSchema.model_validate(payload)
