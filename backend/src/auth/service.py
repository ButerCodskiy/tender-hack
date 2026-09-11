"""Бизнес-логика домена auth."""

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import ClientProfileModel, UserModel, UserRole
from src.auth.repository import UserRepository
from src.auth.schemas import (
    AuthTokenResponseSchema,
    ClientRegisterRequestSchema,
    LoginRequestSchema,
    RefreshTokenRequestSchema,
    UserProfileResponseSchema,
)
from src.chat.models import ChatModel
from src.chat.repository import ChatRepository
from src.core.config import settings
from src.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class AuthService:
    """Сервис управления учетными записями, регистрацией и авторизацией."""

    def __init__(
        self,
        user_repo: UserRepository,
        chat_repo: ChatRepository,
        session: AsyncSession,
    ) -> None:
        """Инициализирует сервис зависимостями репозиториев и сессией."""
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.session = session

    def _build_user_profile(
        self,
        user: UserModel,
        role_code: str | None = None,
        profile: ClientProfileModel | None = None,
    ) -> UserProfileResponseSchema:
        """Формирует Pydantic-схему профиля пользователя."""
        actual_role_code = role_code or (user.role.code if user.role else "")
        client_profile = profile or user.client_profile
        return UserProfileResponseSchema(
            id=user.id,
            role_code=actual_role_code,
            email=user.email,
            full_name=user.full_name,
            company_name=client_profile.company_name
            if client_profile
            else None,
            inn=client_profile.inn if client_profile else None,
            created_at=user.created_at,
        )

    def get_user_profile(self, user: UserModel) -> UserProfileResponseSchema:
        """Возвращает схему профиля пользователя."""
        return self._build_user_profile(user)

    def _create_token_response(
        self,
        user: UserModel,
        role_code: str | None = None,
        profile: ClientProfileModel | None = None,
    ) -> AuthTokenResponseSchema:
        """Выпускает пару токенов и формирует ответ с профилем пользователя."""
        actual_role_code = role_code or (user.role.code if user.role else "")
        access_token = create_access_token(
            user_id=user.id,
            role_code=actual_role_code,
        )
        refresh_token = create_refresh_token(
            user_id=user.id,
            role_code=actual_role_code,
        )
        return AuthTokenResponseSchema(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=self._build_user_profile(
                user, role_code=actual_role_code, profile=profile
            ),
        )

    async def register_client(
        self, data: ClientRegisterRequestSchema
    ) -> AuthTokenResponseSchema:
        """Регистрирует нового клиента, создает профиль и постоянный чат поддержки."""
        existing_user = await self.user_repo.get_by_email(data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "email_already_exists",
                    "message": (
                        "Пользователь с таким адресом электронной почты "
                        "уже зарегистрирован"
                    ),
                },
            )

        role = await self.user_repo.get_or_create_role(
            code=UserRole.CLIENT,
            name="Клиент (Поставщик)",
            description="Пользователь портала поставщиков",
        )

        user = UserModel(
            role_id=role.id,
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            is_active=True,
        )
        user.role = role
        await self.user_repo.create_user(user)

        profile = ClientProfileModel(
            user_id=user.id,
            company_name=data.company_name,
            inn=data.inn,
            kpp=data.kpp,
            phone=data.phone,
        )
        user.client_profile = profile
        await self.user_repo.create_client_profile(profile)

        chat = ChatModel(client_id=user.id)
        await self.chat_repo.create(chat)

        await self.session.commit()

        return self._create_token_response(
            user=user,
            role_code=role.code,
            profile=profile,
        )

    async def login(self, data: LoginRequestSchema) -> AuthTokenResponseSchema:
        """Выполняет вход пользователя по почте и паролю."""
        user = await self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "invalid_credentials",
                    "message": "Неверный адрес электронной почты или пароль",
                },
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "account_disabled",
                    "message": "Учетная запись пользователя деактивирована",
                },
            )

        return self._create_token_response(user)

    async def get_user_by_token(
        self, token: str, expected_type: TokenType = TokenType.ACCESS
    ) -> UserModel:
        """Валидирует JWT-токен и возвращает активного пользователя."""
        try:
            payload = decode_token(token)
        except (InvalidTokenError, ValidationError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "token_expired",
                    "message": (
                        "Срок действия токена истек или токен недействителен"
                    ),
                },
            ) from None

        if payload.type != expected_type:
            error_code = (
                "invalid_token_type"
                if expected_type == TokenType.ACCESS
                else "token_expired"
            )
            message = (
                "Для авторизации запросов требуется токен доступа"
                if expected_type == TokenType.ACCESS
                else "Срок действия токена обновления истек или токен недействителен"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": error_code,
                    "message": message,
                },
            )

        try:
            user_id = UUID(payload.sub)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": (
                        "token_expired"
                        if expected_type == TokenType.REFRESH
                        else "invalid_token"
                    ),
                    "message": (
                        "Некорректный идентификатор пользователя в токене"
                    ),
                },
            ) from None

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": (
                        "token_expired"
                        if expected_type == TokenType.REFRESH
                        else "user_not_found"
                    ),
                    "message": "Пользователь не найден",
                },
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "account_disabled",
                    "message": "Учетная запись пользователя деактивирована",
                },
            )

        return user

    async def refresh_tokens(
        self, data: RefreshTokenRequestSchema
    ) -> AuthTokenResponseSchema:
        """Обновляет пару токенов по действующему токену обновления."""
        user = await self.get_user_by_token(
            data.refresh_token, expected_type=TokenType.REFRESH
        )
        return self._create_token_response(user)
