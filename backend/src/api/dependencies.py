"""Внедрение зависимостей FastAPI транспортного слоя (Auth & Database)."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import UserModel, UserRole
from src.auth.repository import UserRepository
from src.auth.service import AuthService
from src.db.database import async_session_maker

http_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Провайдер асинхронной сессии базы данных."""
    async with async_session_maker() as session:
        try:
            yield session
        except asyncio.CancelledError:
            try:
                await session.rollback()
            except Exception:
                pass
            raise


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_user_repository(session: SessionDep) -> UserRepository:
    """Провайдер репозитория пользователей."""
    return UserRepository(session=session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


async def get_auth_service(session: SessionDep) -> AuthService:
    """Провайдер сервиса аутентификации AuthService."""
    return AuthService(session=session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    auth_header: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    service: AuthServiceDep,
) -> UserModel:
    """Извлекает и верифицирует текущего пользователя по JWT Bearer-токену."""
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует заголовок авторизации Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await service.get_user_by_token(auth_header.credentials)


CurrentUserDep = Annotated[UserModel, Depends(get_current_user)]


def require_role(*allowed_roles: UserRole):
    """Фабрика зависимости для проверки ролей пользователя (RBAC)."""
    async def role_checker(current_user: CurrentUserDep) -> UserModel:
        user_role = current_user.role.name if current_user.role else None
        role_values = [r.value for r in allowed_roles]
        if user_role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ запрещен: недостаточно прав для выполнения операции",
            )
        return current_user

    return role_checker


RoleClientDep = Annotated[UserModel, Depends(require_role(UserRole.CLIENT))]
RoleOperatorDep = Annotated[UserModel, Depends(require_role(UserRole.OPERATOR))]
RoleSupervisorDep = Annotated[UserModel, Depends(require_role(UserRole.SUPERVISOR))]
RoleAdminDep = Annotated[UserModel, Depends(require_role(UserRole.ADMIN))]
