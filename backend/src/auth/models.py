"""Модели базы данных домена auth."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import uuid6
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base

if TYPE_CHECKING:
    from src.operators.models import OperatorProfileModel


class UserRole(StrEnum):
    """Системные роли пользователей платформы."""

    CLIENT = "client"
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class RoleModel(Base):
    """Модель роли пользователя (справочник системных прав доступа)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list["UserModel"]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"<RoleModel id={self.id} code={self.code!r}>"


class UserModel(Base):
    """Модель учетной записи пользователя."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    role_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    role: Mapped["RoleModel"] = relationship(back_populates="users")
    client_profile: Mapped["ClientProfileModel | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    operator_profile: Mapped["OperatorProfileModel | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserModel id={self.id} email={self.email!r}>"


class ClientProfileModel(Base):
    """Модель профиля организации клиента."""

    __tablename__ = "client_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    company_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    inn: Mapped[str | None] = mapped_column(
        String(12), nullable=True, index=True
    )
    kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    user: Mapped["UserModel"] = relationship(back_populates="client_profile")

    def __repr__(self) -> str:
        return (
            f"<ClientProfileModel user_id={self.user_id} "
            f"company_name={self.company_name!r}>"
        )
