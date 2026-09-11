"""Маршруты аутентификации и учетных записей."""

from fastapi import APIRouter, status

from src.api.dependencies import AuthServiceDep, CurrentUserDep
from src.auth.schemas import (
    AuthTokenResponseSchema,
    ClientRegisterRequestSchema,
    LoginRequestSchema,
    RefreshTokenRequestSchema,
    UserProfileResponseSchema,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Профиль текущего пользователя",
    description="Возвращает профиль аутентифицированного пользователя.",
)
async def get_current_user_profile(
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> UserProfileResponseSchema:
    """Возвращает профиль аутентифицированного пользователя."""
    return service.get_user_profile(current_user)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация клиента (поставщика)",
    description=(
        "Создает учетную запись клиента, сохраняет реквизиты профиля "
        "и инициализирует постоянный чат поддержки."
    ),
)
async def register_client(
    data: ClientRegisterRequestSchema,
    service: AuthServiceDep,
) -> AuthTokenResponseSchema:
    """Обрабатывает регистрацию нового клиента и возвращает токены авторизации."""
    return await service.register_client(data)


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Аутентификация пользователя",
    description=(
        "Проверяет адрес электронной почты и пароль пользователя "
        "и возвращает пару токенов авторизации с профилем."
    ),
)
async def login(
    data: LoginRequestSchema,
    service: AuthServiceDep,
) -> AuthTokenResponseSchema:
    """Выполняет аутентификацию пользователя и возвращает токены авторизации."""
    return await service.login(data)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Обновление пары токенов",
    description=(
        "Принимает действующий токен обновления и выпускает новую пару "
        "токенов авторизации."
    ),
)
async def refresh(
    data: RefreshTokenRequestSchema,
    service: AuthServiceDep,
) -> AuthTokenResponseSchema:
    """Выпускает новую пару токенов по действующему токену обновления."""
    return await service.refresh_tokens(data)
