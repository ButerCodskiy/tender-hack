"""Автоматические тесты получения профиля текущего пользователя и авторизации."""

import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.models import UserModel
from src.core.security import create_access_token
from src.main import app


@pytest.fixture
async def test_session(async_session: AsyncSession) -> AsyncSession:
    """Предоставляет изолированную сессию базы данных PostgreSQL с откатом изменений."""
    return async_session


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


async def test_get_me_success(client: AsyncClient) -> None:
    """Проверяет успешное получение профиля с валидным access-токеном."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me_user@example.com",
            "password": "Password123",
            "full_name": "Иванов Иван",
            "company_name": "ООО «Тест»",
            "inn": "7701234567",
        },
    )
    assert reg_resp.status_code == status.HTTP_201_CREATED
    access_token = reg_resp.json()["access_token"]
    user_id = reg_resp.json()["user"]["id"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "me_user@example.com"
    assert data["full_name"] == "Иванов Иван"
    assert data["company_name"] == "ООО «Тест»"
    assert data["inn"] == "7701234567"
    assert data["role_code"] == "client"
    assert "created_at" in data


async def test_get_me_missing_authorization_header(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 401 при отсутствии заголовка Authorization."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "not_authenticated"


async def test_get_me_invalid_token(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при передаче поврежденного токена."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.payload"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "token_expired"


async def test_get_me_expired_token(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при передаче истекшего токена доступа."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "expired_user@example.com", "password": "Password123"},
    )
    user_id = reg_resp.json()["user"]["id"]

    expired_access = create_access_token(
        user_id=user_id,
        role_code="client",
        expires_delta=timedelta(seconds=-10),
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_access}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "token_expired"


async def test_get_me_refresh_token_rejected(client: AsyncClient) -> None:
    """Проверяет ошибку 401 при попытке авторизоваться через refresh-токен."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh_auth@example.com", "password": "Password123"},
    )
    refresh_token = reg_resp.json()["refresh_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "invalid_token_type"


async def test_get_me_deactivated_user(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Проверяет ошибку 403 при запросе от деактивированного пользователя."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "deactivated_me@example.com",
            "password": "Password123",
        },
    )
    access_token = reg_resp.json()["access_token"]
    user_id = uuid.UUID(reg_resp.json()["user"]["id"])

    user = await test_session.get(UserModel, user_id)
    assert user is not None
    user.is_active = False
    await test_session.commit()

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    error_data = response.json()
    assert error_data["detail"]["code"] == "account_disabled"


async def test_get_me_nonexistent_user(client: AsyncClient) -> None:
    """Проверяет ошибку 401 если субъект токена удален из базы данных."""
    random_user_id = uuid.uuid4()
    access_token = create_access_token(
        user_id=random_user_id,
        role_code="client",
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_data = response.json()
    assert error_data["detail"]["code"] == "user_not_found"
