"""Скрипт сидирования демонстрационных пользователей, ролей и линий поддержки."""

import asyncio
import logging

from sqlalchemy import select

from src.auth.models import ClientProfileModel, RoleModel, UserModel, UserRole
from src.chat.models import ChatModel
from src.core.security import hash_password
from src.db.database import async_session_maker
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_demo")


async def seed() -> None:
    """Идемпотентно наполняет базу данных демонстрационными записями."""
    async with async_session_maker() as session:
        roles_data = [
            (
                UserRole.CLIENT,
                "Клиент (Поставщик)",
                "Пользователь портала поставщиков",
            ),
            (
                UserRole.OPERATOR,
                "Оператор поддержки",
                "Специалист линии поддержки",
            ),
            (
                UserRole.SUPERVISOR,
                "Руководитель поддержки",
                "Контроль качества и супервизия",
            ),
            (
                UserRole.ADMIN,
                "Системный администратор",
                "Полный доступ к системе",
            ),
        ]

        roles: dict[str, RoleModel] = {}
        for code, name, desc in roles_data:
            stmt = select(RoleModel).where(RoleModel.code == code)
            role = (await session.scalars(stmt)).first()
            if not role:
                role = RoleModel(code=code, name=name, description=desc)
                session.add(role)
                await session.flush()
                logger.info("Создана роль: %s", code)
            roles[code] = role

        stmt_line = select(SupportLineModel).where(
            SupportLineModel.code == "general"
        )
        line = (await session.scalars(stmt_line)).first()
        if not line:
            line = SupportLineModel(
                code="general",
                name="Регламенты и сопровождение процедур",
                description="Первая линия консультаций по регламенту портала",
                is_active=True,
            )
            session.add(line)
            await session.flush()
            logger.info("Создана линия поддержки: general")

        # Сидирование демонстрационных пользователей (пароль: password123)
        default_pwd_hash = hash_password("password123")

        # Клиент-поставщик
        supplier_email = "supplier@example.com"
        stmt_user = select(UserModel).where(UserModel.email == supplier_email)
        supplier = (await session.scalars(stmt_user)).first()
        if not supplier:
            supplier = UserModel(
                role_id=roles[UserRole.CLIENT].id,
                email=supplier_email,
                password_hash=default_pwd_hash,
                full_name="Иванов Иван Иванович",
                is_active=True,
            )
            session.add(supplier)
            await session.flush()

            profile = ClientProfileModel(
                user_id=supplier.id,
                company_name="ООО «ТехноСнаб Поставка»",
                inn="7701234567",
                kpp="770101001",
                phone="+7 (495) 123-45-67",
            )
            session.add(profile)

            chat = ChatModel(client_id=supplier.id)
            session.add(chat)
            logger.info("Создан тестовый поставщик: %s", supplier_email)

        # Оператор
        operator_email = "operator1@example.com"
        stmt_op = select(UserModel).where(UserModel.email == operator_email)
        operator = (await session.scalars(stmt_op)).first()
        if not operator:
            operator = UserModel(
                role_id=roles[UserRole.OPERATOR].id,
                email=operator_email,
                password_hash=default_pwd_hash,
                full_name="Смирнова Анна Сергеевна",
                is_active=True,
            )
            session.add(operator)
            await session.flush()

            op_profile = OperatorProfileModel(
                user_id=operator.id,
                line_id=line.id,
                shift_status=OperatorShiftStatus.ACTIVE,
                max_slots=5,
            )
            session.add(op_profile)
            logger.info("Создан тестовый оператор: %s", operator_email)

        # Руководитель (супервизор)
        admin_email = "admin@example.com"
        stmt_admin = select(UserModel).where(UserModel.email == admin_email)
        admin_user = (await session.scalars(stmt_admin)).first()
        if not admin_user:
            admin_user = UserModel(
                role_id=roles[UserRole.SUPERVISOR].id,
                email=admin_email,
                password_hash=default_pwd_hash,
                full_name="Ковалев Михаил Петрович",
                is_active=True,
            )
            session.add(admin_user)
            await session.flush()

            admin_profile = OperatorProfileModel(
                user_id=admin_user.id,
                line_id=line.id,
                shift_status=OperatorShiftStatus.ACTIVE,
                max_slots=10,
            )
            session.add(admin_profile)
            logger.info("Создан тестовый супервизор: %s", admin_email)

        await session.commit()
        logger.info("Сидирование демонстрационных данных успешно завершено.")


if __name__ == "__main__":
    asyncio.run(seed())
