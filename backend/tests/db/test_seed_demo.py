"""Тесты проверки корректности сидирования демонстрационных данных (seed_demo.py)."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RoleModel, UserModel, UserRole
from src.chat.models import ChatModel, TicketModel
from src.core.security import verify_password
from src.db.seed_demo import seed
from src.main import app
from src.operators.models import OperatorProfileModel, SupportLineModel


async def test_seed_demo_roles_and_lines_exist(
    async_session: AsyncSession,
) -> None:
    """Проверяет наличие всех системных ролей и линий поддержки."""
    roles = (await async_session.scalars(select(RoleModel))).all()
    role_codes = {role.code for role in roles}
    for expected_role in [
        UserRole.CLIENT,
        UserRole.OPERATOR,
        UserRole.SUPERVISOR,
        UserRole.ADMIN,
    ]:
        assert expected_role in role_codes

    lines = (await async_session.scalars(select(SupportLineModel))).all()
    line_codes = {line.code for line in lines}
    assert {"L1", "L2", "L3"}.issubset(line_codes)


async def test_seed_demo_users_and_passwords(
    async_session: AsyncSession,
) -> None:
    """Проверяет наличие демонстрационных пользователей и валидность их паролей."""
    expected_emails = [
        "supplier@example.com",
        "operator1@example.com",
        "operator2@example.com",
        "operator3@example.com",
        "admin@example.com",
    ]
    for email in expected_emails:
        stmt = select(UserModel).where(UserModel.email == email)
        user = (await async_session.scalars(stmt)).first()
        assert user is not None, f"Пользователь {email} должен существовать"
        assert verify_password("password123", user.password_hash)
        assert user.is_active is True


async def test_seed_demo_tickets_and_operators(
    async_session: AsyncSession,
) -> None:
    """Проверяет создание профилей операторов и демонстрационных тикетов."""
    operators = (
        await async_session.scalars(select(OperatorProfileModel))
    ).all()
    assert len(operators) >= 1

    tickets = (await async_session.scalars(select(TicketModel))).all()
    assert len(tickets) >= 1

    chats = (await async_session.scalars(select(ChatModel))).all()
    assert len(chats) >= 1


async def test_seed_demo_idempotency(async_session: AsyncSession) -> None:
    """Проверяет, что повторный вызов seed() безопасен и не падает."""
    await seed()


async def test_seed_demo_supplier_login() -> None:
    """Проверяет возможность авторизации сидированного пользователя через API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "supplier@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "supplier@example.com"
        assert data["user"]["role_code"] == "client"
