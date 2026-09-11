"""Слой доступа к данным домена auth."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.auth.models import ClientProfileModel, RoleModel, UserModel


class UserRepository:
    """Репозиторий для работы с учетными записями, ролями и профилями."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий активной сессией базы данных."""
        self.session = session

    async def get_by_id(self, user_id: UUID) -> UserModel | None:
        """Извлекает пользователя по первичному ключу с подгрузкой роли и профиля."""
        stmt = (
            select(UserModel)
            .options(
                joinedload(UserModel.role),
                joinedload(UserModel.client_profile),
            )
            .where(UserModel.id == user_id)
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_by_email(self, email: str) -> UserModel | None:
        """Находит пользователя по адресу электронной почты."""
        stmt = (
            select(UserModel)
            .options(
                joinedload(UserModel.role),
                joinedload(UserModel.client_profile),
            )
            .where(UserModel.email == email)
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_role_by_code(self, code: str) -> RoleModel | None:
        """Находит роль по уникальному символьному коду."""
        stmt = select(RoleModel).where(RoleModel.code == code)
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_or_create_role(
        self, code: str, name: str, description: str | None = None
    ) -> RoleModel:
        """Получает роль или создает новую запись справочника, если она отсутствует."""
        role = await self.get_role_by_code(code)
        if not role:
            role = RoleModel(code=code, name=name, description=description)
            self.session.add(role)
            await self.session.flush()
        return role

    async def create_user(self, user: UserModel) -> UserModel:
        """Добавляет новую учетную запись пользователя в сессию."""
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_client_profile(
        self, profile: ClientProfileModel
    ) -> ClientProfileModel:
        """Добавляет профиль организации клиента в сессию."""
        self.session.add(profile)
        await self.session.flush()
        return profile
