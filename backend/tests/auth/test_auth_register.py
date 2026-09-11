"""Тесты регистрации клиентов и базового контура безопасности."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.models import ClientProfileModel, UserModel
from src.chat.models import ChatModel
from src.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.db.database import Base, async_session_maker, engine
from src.main import app


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Гарантирует наличие схемы таблиц и очищает данные перед каждым тестом."""
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
    """Создает тестовый HTTP-клиент с переопределенной сессией БД."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


def test_password_hashing_and_verification() -> None:
    """Проверяет корректность хеширования и сверки паролей."""
    raw_password = "SecretPassword123"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation_and_decoding() -> None:
    """Проверяет выпуск и валидацию JWT токенов доступа и обновления."""
    user_id = uuid.uuid4()
    role_code = "client"

    access_token = create_access_token(user_id=user_id, role_code=role_code)
    refresh_token = create_refresh_token(user_id=user_id, role_code=role_code)

    decoded_access = decode_token(access_token)
    assert decoded_access.sub == str(user_id)
    assert decoded_access.role == role_code
    assert decoded_access.type == TokenType.ACCESS
    assert decoded_access.exp > 0
    assert decoded_access.iat > 0

    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh.sub == str(user_id)
    assert decoded_refresh.role == role_code
    assert decoded_refresh.type == TokenType.REFRESH


async def test_register_client_success_full(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Проверяет успешную регистрацию клиента со всеми реквизитами."""
    payload = {
        "email": "supplier_full@example.com",
        "password": "SecretPassword123",
        "full_name": "Иванов Иван Иванович",
        "company_name": "ООО «Поставка-Плюс»",
        "inn": "7701234567",
        "kpp": "770101001",
        "phone": "+79991234567",
    }

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900

    user_data = data["user"]
    user_id = uuid.UUID(user_data["id"])
    assert user_data["email"] == payload["email"]
    assert user_data["role_code"] == "client"
    assert user_data["full_name"] == payload["full_name"]
    assert user_data["company_name"] == payload["company_name"]
    assert user_data["inn"] == payload["inn"]
    assert "created_at" in user_data

    # Проверка сохранения в базе данных PostgreSQL
    user_in_db = await test_session.get(UserModel, user_id)
    assert user_in_db is not None
    assert user_in_db.email == payload["email"]
    assert user_in_db.password_hash != payload["password"]
    assert (
        verify_password(payload["password"], user_in_db.password_hash) is True
    )

    profile_in_db = await test_session.get(ClientProfileModel, user_id)
    assert profile_in_db is not None
    assert profile_in_db.company_name == payload["company_name"]
    assert profile_in_db.inn == payload["inn"]
    assert profile_in_db.kpp == payload["kpp"]
    assert profile_in_db.phone == payload["phone"]

    # Проверка создания связанного чата
    chat_stmt = select(ChatModel).where(ChatModel.client_id == user_id)
    chat_result = await test_session.scalars(chat_stmt)
    chat_in_db = chat_result.first()
    assert chat_in_db is not None
    assert chat_in_db.client_id == user_id


async def test_register_client_success_minimal(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Проверяет успешную регистрацию клиента только с обязательными полями."""
    payload = {
        "email": "supplier_min@example.com",
        "password": "MinimalPassword123",
    }

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    user_data = data["user"]
    assert user_data["email"] == payload["email"]
    assert user_data["full_name"] is None
    assert user_data["company_name"] is None
    assert user_data["inn"] is None

    # Чат должен быть создан даже при минимальной регистрации
    user_id = uuid.UUID(user_data["id"])
    chat_stmt = select(ChatModel).where(ChatModel.client_id == user_id)
    chat_result = await test_session.scalars(chat_stmt)
    assert chat_result.first() is not None


async def test_register_client_duplicate_email_conflict(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 409 Conflict при повторной регистрации на занятый email."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123",
    }

    first_resp = await client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == status.HTTP_201_CREATED

    second_resp = await client.post("/api/v1/auth/register", json=payload)
    assert second_resp.status_code == status.HTTP_409_CONFLICT
    error_data = second_resp.json()
    assert error_data["detail"]["code"] == "email_already_exists"


async def test_register_client_validation_password_too_short(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 422 при слишком коротком пароле (< 8 символов)."""
    payload = {
        "email": "short_pwd@example.com",
        "password": "short",
    }

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_register_client_validation_invalid_inn(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 422 при некорректной длине или символах в ИНН."""
    # 9 цифр (недопустимо: должно быть 10 или 12)
    resp1 = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad_inn1@example.com",
            "password": "Password123",
            "inn": "123456789",
        },
    )
    assert resp1.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Буквы в ИНН
    resp2 = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad_inn2@example.com",
            "password": "Password123",
            "inn": "1234567890AB",
        },
    )
    assert resp2.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_register_client_validation_invalid_kpp(
    client: AsyncClient,
) -> None:
    """Проверяет ошибку 422 при некорректном КПП (не 9 цифр)."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad_kpp@example.com",
            "password": "Password123",
            "kpp": "12345",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
