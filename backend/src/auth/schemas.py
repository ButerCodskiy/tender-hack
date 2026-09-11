"""Схемы валидации данных домена auth."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ClientRegisterRequestSchema(BaseModel):
    """Схема запроса регистрации нового клиента."""

    email: EmailStr = Field(
        ...,
        description="Электронная почта для входа",
        examples=["supplier@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль пользователя",
        examples=["SecretPass123"],
    )
    full_name: str | None = Field(
        None,
        max_length=255,
        description="ФИО контактного лица (опционально)",
        examples=["Иванов Иван Иванович"],
    )
    company_name: str | None = Field(
        None,
        max_length=255,
        description="Наименование организации или ИП (опционально)",
        examples=["ООО «Поставка-Плюс»"],
    )
    inn: str | None = Field(
        None,
        description="ИНН организации (10) или ИП (12) (опционально)",
        examples=["7701234567"],
    )
    kpp: str | None = Field(
        None,
        description="КПП для юридических лиц (опционально)",
        examples=["770101001"],
    )
    phone: str | None = Field(
        None,
        max_length=32,
        description="Контактный номер телефона (опционально)",
        examples=["+79991234567"],
    )

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value: str | None) -> str | None:
        """Проверяет длину и формат ИНН при наличии значения."""
        if value is not None and (
            not value.isdigit() or len(value) not in (10, 12)
        ):
            raise ValueError("ИНН должен содержать ровно 10 или 12 цифр")
        return value

    @field_validator("kpp")
    @classmethod
    def validate_kpp(cls, value: str | None) -> str | None:
        """Проверяет длину и формат КПП при наличии значения."""
        if value is not None and (not value.isdigit() or len(value) != 9):
            raise ValueError("КПП должен содержать ровно 9 цифр")
        return value


class LoginRequestSchema(BaseModel):
    """Схема запроса аутентификации пользователя."""

    email: EmailStr = Field(
        ...,
        description="Электронная почта",
        examples=["operator1@example.com"],
    )
    password: str = Field(
        ...,
        description="Пароль",
        examples=["OperatorPass123"],
    )


class RefreshTokenRequestSchema(BaseModel):
    """Схема запроса обновления токенов авторизации."""

    refresh_token: str = Field(
        ...,
        description="Действующий токен обновления",
    )


class UserProfileResponseSchema(BaseModel):
    """Схема профиля зарегистрированного пользователя."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор пользователя")
    role_code: str = Field(
        ...,
        description="Код роли пользователя",
        examples=["client"],
    )
    email: EmailStr = Field(..., description="Электронная почта")
    full_name: str | None = Field(
        None,
        description="ФИО пользователя (при наличии)",
    )
    company_name: str | None = Field(
        None,
        description="Наименование организации (при наличии)",
    )
    inn: str | None = Field(
        None,
        description="ИНН организации (при наличии)",
    )
    created_at: datetime = Field(..., description="Время регистрации")


class AuthTokenResponseSchema(BaseModel):
    """Схема ответа с парой токенов авторизации."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="Токен доступа JWT")
    refresh_token: str = Field(..., description="Токен обновления JWT")
    token_type: str = Field("bearer", description="Тип токена")
    expires_in: int = Field(
        900,
        description="Время действия токена доступа в секундах",
    )
    user: UserProfileResponseSchema = Field(
        ...,
        description="Профиль пользователя",
    )
