"""Внедрение зависимостей FastAPI транспортного слоя."""

import asyncio
from collections.abc import AsyncGenerator, Iterable
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.repository import AnalyticsRepository
from src.analytics.service import AnalyticsService
from src.auth.models import UserModel, UserRole
from src.auth.repository import UserRepository
from src.auth.service import AuthService
from src.chat.repository import ChatRepository, TicketRepository
from src.chat.service import ChatService
from src.core.redis_client import (
    RedisChatContext,
    RedisLineQueue,
    RedisOperatorEvents,
    RedisTicketEvents,
)
from src.db.database import async_session_maker
from src.kb.repository import KbRepository
from src.kb.service import KbService
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.service import OperatorService
from src.rag.service import RagService

http_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Провайдер асинхронной сессии базы данных."""
    async with async_session_maker() as session:
        try:
            yield session
        except asyncio.CancelledError:
            # Запрос прерван клиентом (перезагрузка страницы/разрыв соединения).
            # Выполняем безопасный откат незавершенной транзакции без падения пула.
            try:
                await session.rollback()
            except Exception:
                pass
            raise


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_rag_service() -> RagService:
    """Провайдер сервиса поискового ядра RagService."""
    return RagService()


RagServiceDep = Annotated[RagService, Depends(get_rag_service)]


async def get_chat_repository(session: SessionDep) -> ChatRepository:
    """Провайдер репозитория чатов."""
    return ChatRepository(session=session)


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]


async def get_ticket_repository(session: SessionDep) -> TicketRepository:
    """Провайдер репозитория обращений."""
    return TicketRepository(session=session)


TicketRepositoryDep = Annotated[
    TicketRepository, Depends(get_ticket_repository)
]


async def get_support_line_repository(
    session: SessionDep,
) -> SupportLineRepository:
    """Провайдер репозитория линий поддержки."""
    return SupportLineRepository(session=session)


SupportLineRepositoryDep = Annotated[
    SupportLineRepository, Depends(get_support_line_repository)
]


def get_redis(request: Request) -> aioredis.Redis:
    """Провайдер клиента Redis из состояния приложения."""
    redis: aioredis.Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise RuntimeError(
            "Клиент Redis не инициализирован в состоянии приложения (app.state.redis)."
        )
    return redis


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]


def get_redis_context(
    redis: RedisDep,
) -> RedisChatContext:
    """Провайдер оперативного контекста диалога в Redis."""
    return RedisChatContext(redis=redis)


RedisContextDep = Annotated[RedisChatContext, Depends(get_redis_context)]


def get_redis_line_queue(
    redis: RedisDep,
) -> RedisLineQueue:
    """Провайдер очереди обращений в Redis."""
    return RedisLineQueue(redis=redis)


RedisLineQueueDep = Annotated[RedisLineQueue, Depends(get_redis_line_queue)]


def get_redis_operator_events(redis: RedisDep) -> RedisOperatorEvents:
    """Провайдер шины событий операторов в Redis Pub/Sub."""
    return RedisOperatorEvents(redis=redis)


RedisOperatorEventsDep = Annotated[
    RedisOperatorEvents, Depends(get_redis_operator_events)
]


def get_redis_ticket_events(redis: RedisDep) -> RedisTicketEvents:
    """Провайдер шины событий тикетов в Redis Pub/Sub."""
    return RedisTicketEvents(redis=redis)


RedisTicketEventsDep = Annotated[
    RedisTicketEvents, Depends(get_redis_ticket_events)
]


async def get_chat_service(
    repo: ChatRepositoryDep,
    session: SessionDep,
    rag_service: RagServiceDep,
    ticket_repo: TicketRepositoryDep,
    redis_context: RedisContextDep,
    ticket_events: RedisTicketEventsDep,
    line_queue: RedisLineQueueDep,
) -> ChatService:
    """Провайдер сервиса диалогов ChatService."""
    return ChatService(
        repo=repo,
        session=session,
        rag_service=rag_service,
        ticket_repo=ticket_repo,
        redis_context=redis_context,
        ticket_events=ticket_events,
        line_queue=line_queue,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


async def get_user_repository(session: SessionDep) -> UserRepository:
    """Провайдер репозитория учетных записей."""
    return UserRepository(session=session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


async def get_auth_service(
    user_repo: UserRepositoryDep,
    chat_repo: ChatRepositoryDep,
    session: SessionDep,
) -> AuthService:
    """Провайдер сервиса аутентификации AuthService."""
    return AuthService(
        user_repo=user_repo,
        chat_repo=chat_repo,
        session=session,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(http_bearer)
    ],
    auth_service: AuthServiceDep,
) -> UserModel:
    """Извлекает и валидирует текущего пользователя по JWT-токену доступа."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "not_authenticated",
                "message": (
                    "Отсутствует заголовок авторизации или передан "
                    "неверный тип токена"
                ),
            },
        )

    return await auth_service.get_user_by_token(credentials.credentials)


CurrentUserDep = Annotated[UserModel, Depends(get_current_user)]


async def get_current_user_sse(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(http_bearer)
    ],
    auth_service: AuthServiceDep,
    token: Annotated[
        str | None,
        Query(
            alias="token",
            description="JWT-токен доступа для браузерного EventSource",
        ),
    ] = None,
) -> UserModel:
    """Извлекает и валидирует пользователя для постоянных SSE-соединений.

    Поддерживает передачу токена как через заголовок Authorization: Bearer <token>,
    так и через query-параметр ?token=<token> для нативного EventSource.
    """
    raw_token: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        raw_token = credentials.credentials
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "not_authenticated",
                "message": (
                    "Отсутствует токен авторизации (передайте заголовок "
                    "Authorization: Bearer <token> или query-параметр ?token=<token>)"
                ),
            },
        )

    return await auth_service.get_user_by_token(raw_token)


CurrentUserSseDep = Annotated[UserModel, Depends(get_current_user_sse)]


class AccessDeniedException(HTTPException):
    """Исключение при отказе в доступе по ролевой модели (403 Forbidden)."""

    def __init__(
        self,
        message: str = "Недостаточно прав для выполнения данной операции",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "access_denied",
                "message": message,
            },
        )


def _extract_role_code(current_user: UserModel) -> str | None:
    """Безопасно извлекает строковый код роли пользователя без триггера MissingGreenlet."""
    if hasattr(current_user, "__dict__") and "role" in current_user.__dict__:
        role = current_user.__dict__["role"]
        if role is not None:
            return getattr(role, "code", None)
        return None
    try:
        role = getattr(current_user, "role", None)
        return getattr(role, "code", None)
    except Exception:
        return None


class RoleChecker:
    """Универсальная зависимость для проверки роли пользователя на HTTP REST маршрутах."""

    def __init__(self, allowed_roles: Iterable[UserRole | str]) -> None:
        self.allowed_roles: frozenset[str] = frozenset(
            r.value if isinstance(r, UserRole) else str(r)
            for r in allowed_roles
        )

    def _check(self, current_user: UserModel) -> UserModel:
        role_code = _extract_role_code(current_user)
        if not role_code or role_code not in self.allowed_roles:
            if self.allowed_roles == {
                UserRole.OPERATOR.value,
                UserRole.SUPERVISOR.value,
                UserRole.ADMIN.value,
            }:
                msg = "Доступ разрешен только операторам поддержки"
            elif self.allowed_roles == {UserRole.CLIENT.value}:
                msg = "Доступ разрешен только клиентам"
            elif self.allowed_roles == {
                UserRole.SUPERVISOR.value,
                UserRole.ADMIN.value,
            }:
                msg = "Доступ разрешен только супервизорам и администраторам"
            elif self.allowed_roles == {UserRole.ADMIN.value}:
                msg = "Доступ разрешен только администраторам"
            else:
                msg = "Недостаточно прав для выполнения данной операции"
            raise AccessDeniedException(message=msg)
        return current_user

    async def __call__(self, current_user: CurrentUserDep) -> UserModel:
        return self._check(current_user)


class RoleCheckerSse(RoleChecker):
    """Универсальная зависимость для проверки роли пользователя на постоянных SSE-соединениях."""

    async def __call__(self, current_user: CurrentUserSseDep) -> UserModel:
        return self._check(current_user)


def require_roles(
    *roles: UserRole | str, sse: bool = False
) -> RoleChecker | RoleCheckerSse:
    """Фабрика зависимостей проверки ролей для FastAPI."""
    if sse:
        return RoleCheckerSse(roles)
    return RoleChecker(roles)


def require_roles_sse(*roles: UserRole | str) -> RoleCheckerSse:
    """Фабрика зависимостей проверки ролей для постоянных SSE-соединений."""
    return RoleCheckerSse(roles)


# Типизированные зависимости пользователей с проверкой ролей
CurrentClientDep = Annotated[
    UserModel, Depends(require_roles(UserRole.CLIENT))
]
CurrentClientSseDep = Annotated[
    UserModel, Depends(require_roles_sse(UserRole.CLIENT))
]

CurrentOperatorDep = Annotated[
    UserModel,
    Depends(
        require_roles(UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN)
    ),
]
CurrentOperatorSseDep = Annotated[
    UserModel,
    Depends(
        require_roles_sse(
            UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN
        )
    ),
]

CurrentSupervisorDep = Annotated[
    UserModel,
    Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN)),
]

CurrentAdminDep = Annotated[
    UserModel,
    Depends(require_roles(UserRole.ADMIN)),
]


async def require_operator_user(
    current_user: CurrentUserDep,
) -> UserModel:
    """Проверяет наличие роли оператора, супервизора или администратора (обратная совместимость)."""
    checker = require_roles(
        UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN
    )
    return checker._check(current_user)


async def require_operator_user_sse(
    current_user: CurrentUserSseDep,
) -> UserModel:
    """Проверяет права доступа оператора для постоянного соединения SSE (обратная совместимость)."""
    checker = require_roles_sse(
        UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN
    )
    return checker._check(current_user)


async def get_kb_repository(session: SessionDep) -> KbRepository:
    """Провайдер репозитория нормативной базы знаний."""
    return KbRepository(session=session)


KbRepositoryDep = Annotated[KbRepository, Depends(get_kb_repository)]


async def get_kb_service(
    repo: KbRepositoryDep,
    session: SessionDep,
) -> KbService:
    """Провайдер сервиса базы знаний KbService."""
    return KbService(repo=repo, session=session)


KbServiceDep = Annotated[KbService, Depends(get_kb_service)]


async def get_operator_repository(session: SessionDep) -> OperatorRepository:
    """Провайдер репозитория операторов."""
    return OperatorRepository(session=session)


OperatorRepositoryDep = Annotated[
    OperatorRepository, Depends(get_operator_repository)
]


async def get_operator_service(
    session: SessionDep,
    redis: RedisDep,
    operator_repo: OperatorRepositoryDep,
    support_line_repo: SupportLineRepositoryDep,
    ticket_repo: TicketRepositoryDep,
    line_queue: RedisLineQueueDep,
    redis_events: RedisOperatorEventsDep,
    ticket_events: RedisTicketEventsDep,
    chat_context: RedisContextDep,
) -> OperatorService:
    """Провайдер сервиса операторов OperatorService."""
    return OperatorService(
        session=session,
        redis=redis,
        operator_repo=operator_repo,
        support_line_repo=support_line_repo,
        ticket_repo=ticket_repo,
        line_queue=line_queue,
        redis_events=redis_events,
        ticket_events=ticket_events,
        chat_context=chat_context,
    )


OperatorServiceDep = Annotated[OperatorService, Depends(get_operator_service)]


async def get_analytics_repository(session: SessionDep) -> AnalyticsRepository:
    """Провайдер репозитория аналитики и контроля качества."""
    return AnalyticsRepository(session=session)


AnalyticsRepositoryDep = Annotated[
    AnalyticsRepository, Depends(get_analytics_repository)
]


async def get_analytics_service(
    session: SessionDep,
    redis: RedisDep,
) -> AnalyticsService:
    """Провайдер сервиса аналитики и контроля качества AnalyticsService."""
    return AnalyticsService(session=session, redis=redis)


AnalyticsServiceDep = Annotated[
    AnalyticsService, Depends(get_analytics_service)
]
