"""Автоматические тесты аутентификации пользователей и обновления токенов."""

import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.models import UserModel
from src.core.security import (
    TokenType,
    create_refresh_token,
    decode_token,
)
from src.db.database import Base, async_session_maker, engine
from src.main import app


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Обеспечивает наличие таблиц и очищает данные перед каждым тестом."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE chats, client_profiles, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE chats, client_profiles, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Предоставляет тестовую сессию базы данных PostgreSQL."""
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def client(
    test_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Создает тестовый HTTP-клиент с изолированной сессией базы данных."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


async def test_login_success(client: AsyncClient) -> None:
    """Проверяет успешный вход зарегистрированного пользователя."""
    register_payload = {
        "email": "user_login@example.com",
        "password": "CorrectPassword123",
        "full_name": "Тестовый Пользователь",
        "company_name": "ООО «Тест»",
        "inn": "7701234567",
    }
    reg_resp = await client.post(
        "/api/v1/auth/register", json=register_payload
    )
    assert reg_resp.status_code == status.HTTP_201_CREATED

    login_payload = {
        "email": "user_login@example.com",
        "password": "CorrectPassword123",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900

    user_info = data["user"]
    assert user_info["email"] == "user_login@example.com"
    assert user_info["full_name"] == "Тестовый Пользователь"
    assert user_info["company_name"] == "ООО «Тест»"
    assert user_info["inn"] == "7701234567"
    assert user_info["role_code"] == "client"

    access_payload = decode_token(data["access_token"])
    assert access_payload.type == TokenType.ACCESS
    assert access_payload.sub == user_info["id"]

    refresh_payload = decode_token(data["refresh_token"])
    assert refresh_payload.type == TokenType.REFRESH
    assert refresh_payload.sub == user_info["id"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при передаче неверного пароля."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong_pwd@example.com",
            "password": "OriginalPassword123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong_pwd@example.com",
            "password": "WrongPassword456",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "invalid_credentials"
    assert (
        error_data["detail"]["message"]
        == "Неверный адрес электронной почты или пароль"
    )


async def test_login_nonexistent_email(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при попытке входа с незарегистрированной почтой."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "AnyPassword123",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "invalid_credentials"
    assert (
        error_data["detail"]["message"]
        == "Неверный адрес электронной почты или пароль"
    )


async def test_login_deactivated_user(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Проверяет ошибку 403 при попытке входа деактивированного пользователя."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "disabled@example.com", "password": "Password123"},
    )
    user_id = uuid.UUID(reg_resp.json()["user"]["id"])

    user = await test_session.get(UserModel, user_id)
    assert user is not None
    user.is_active = False
    await test_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": "Password123"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    error_data = response.json()
    assert error_data["detail"]["code"] == "account_disabled"
    assert (
        error_data["detail"]["message"]
        == "Учетная запись пользователя деактивирована"
    )


async def test_refresh_tokens_success(client: AsyncClient) -> None:
    """Проверяет успешный выпуск новой пары токенов по refresh-токену."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh_ok@example.com", "password": "Password123"},
    )
    initial_refresh = reg_resp.json()["refresh_token"]
    user_id = reg_resp.json()["user"]["id"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": initial_refresh},
    )
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900
    assert data["user"]["id"] == user_id
    assert data["user"]["email"] == "refresh_ok@example.com"

    new_access = decode_token(data["access_token"])
    assert new_access.type == TokenType.ACCESS
    assert new_access.sub == user_id

    new_refresh = decode_token(data["refresh_token"])
    assert new_refresh.type == TokenType.REFRESH
    assert new_refresh.sub == user_id


async def test_refresh_tokens_with_access_token_fails(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 401 при попытке использовать access-токен вместо refresh."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "access_as_refresh@example.com",
            "password": "Password123",
        },
    )
    access_token = reg_resp.json()["access_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "token_expired"


async def test_refresh_tokens_expired(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 401 при передаче просроченного refresh-токена."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired_refresh@example.com",
            "password": "Password123",
        },
    )
    user_id = reg_resp.json()["user"]["id"]

    expired_token = create_refresh_token(
        user_id=user_id,
        role_code="client",
        expires_delta=timedelta(seconds=-10),
    )

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_token},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "token_expired"


async def test_refresh_tokens_invalid_string(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при передаче поврежденного или произвольного токена."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "malformed.jwt.token"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "token_expired"


async def test_refresh_tokens_deactivated_user(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Проверяет ошибку 403 при обновлении токена для деактивированного пользователя."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh_disabled@example.com",
            "password": "Password123",
        },
    )
    refresh_token = reg_resp.json()["refresh_token"]
    user_id = uuid.UUID(reg_resp.json()["user"]["id"])

    user = await test_session.get(UserModel, user_id)
    assert user is not None
    user.is_active = False
    await test_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    error_data = response.json()
    assert error_data["detail"]["code"] == "account_disabled"
    assert (
        error_data["detail"]["message"]
        == "Учетная запись пользователя деактивирована"
    )
