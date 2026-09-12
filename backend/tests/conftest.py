"""Глобальные фикстуры тестового окружения на базе Testcontainers.

Паттерн: session-scoped контейнеры PostgreSQL и Redis,
полностью изолирующие тесты от рабочей базы данных и очередей из docker-compose.yml.
"""

import os
import warnings
from collections.abc import AsyncGenerator, Generator

# Защита от поврежденной переменной SSL_CERT_FILE (Windows)
if "SSL_CERT_FILE" in os.environ and not os.path.isfile(
    os.environ["SSL_CERT_FILE"]
):
    os.environ.pop("SSL_CERT_FILE", None)

# Отключаем Ryuk для Docker Desktop на Windows во избежание сбоев проброса портов
os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

import pytest
import redis.asyncio as aioredis
from testcontainers.postgres import PostgresContainer

try:
    from testcontainers.community.redis import RedisContainer
except ImportError:
    from testcontainers.redis import RedisContainer

# Запускаем контейнеры ДО первого импорта src.core.config и src.db.database,
# чтобы Pydantic Settings и SQLAlchemy Engine прочитали динамические порты контейнеров!
_pg_container: PostgresContainer | None = None
_redis_container: RedisContainer | None = None

try:
    _pg_container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    _pg_container.start()
    os.environ["DB_HOST"] = _pg_container.get_container_host_ip()
    os.environ["DB_PORT"] = str(_pg_container.get_exposed_port(5432))
    os.environ["DB_USER"] = _pg_container.username
    os.environ["DB_PASS"] = _pg_container.password
    os.environ["DB_NAME"] = _pg_container.dbname
except Exception as e:
    warnings.warn(
        f"Не удалось запустить Testcontainers Postgres: {e}", stacklevel=2
    )
    _pg_container = None

try:
    _redis_container = RedisContainer("redis:7-alpine")
    _redis_container.start()
    os.environ["REDIS_HOST"] = _redis_container.get_container_host_ip()
    os.environ["REDIS_PORT"] = str(_redis_container.get_exposed_port(6379))
    os.environ["REDIS_DB"] = "0"
except Exception as e:
    warnings.warn(
        f"Не удалось запустить Testcontainers Redis: {e}", stacklevel=2
    )
    _redis_container = None

# Теперь импортируем настройки и базу данных — они подключаются к тестовым контейнерам!
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession  # noqa: E402

from src.auth.models import RoleModel, UserRole  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.db.database import Base, engine  # noqa: E402
from src.operators.models import SupportLineModel  # noqa: E402


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Останавливает тестовые контейнеры по завершении всей тестовой сессии."""
    if _pg_container is not None:
        try:
            _pg_container.stop()
        except Exception:
            pass
    if _redis_container is not None:
        try:
            _redis_container.stop()
        except Exception:
            pass


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Предоставляет инстанс контейнера PostgreSQL на время сессии."""
    if _pg_container is None:
        pytest.skip(
            "Docker / Testcontainers PostgreSQL недоступен в текущем окружении"
        )
    yield _pg_container


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Предоставляет инстанс контейнера Redis на время сессии."""
    if _redis_container is None:
        pytest.skip(
            "Docker / Testcontainers Redis недоступен в текущем окружении"
        )
    yield _redis_container


@pytest.fixture(scope="session")
async def async_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Предоставляет сессионный асинхронный движок, привязанный к Testcontainers."""
    yield engine


@pytest.fixture(scope="session", autouse=True)
async def init_test_db(
    async_engine: AsyncEngine,
) -> AsyncGenerator[None, None]:
    """Создает таблицы и наполняет базу демонстрационными данными один раз на сессию."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Сидирование демонстрационных данных через seed_demo
    from src.db.seed_demo import seed

    await seed()

    yield

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()


@pytest.fixture(scope="function")
async def async_session(
    async_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Создает изолированную сессию базы данных для теста с откатом через savepoint."""
    connection = await async_engine.connect()
    transaction = await connection.begin()

    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest.fixture
async def redis_client(
    redis_container: RedisContainer,
) -> AsyncGenerator[aioredis.Redis, None]:
    """Предоставляет асинхронный клиент Redis для тестов с очисткой тестовой базы."""
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
    try:
        await client.flushdb()
    except Exception:
        pass
    await client.aclose()


@pytest.fixture(autouse=True)
async def setup_test_redis(
    redis_client: aioredis.Redis,
) -> AsyncGenerator[None, None]:
    """Гарантирует наличие клиента Redis в app.state для тестов HTTP-обработчиков."""
    from src.main import app

    app.state.redis = redis_client
    yield
    if hasattr(app.state, "redis"):
        delattr(app.state, "redis")


@pytest.fixture
async def client_role(async_session: AsyncSession) -> RoleModel:
    """Возвращает сидированную роль клиента."""
    stmt = select(RoleModel).where(RoleModel.code == UserRole.CLIENT)
    role = (await async_session.scalars(stmt)).first()
    assert role is not None, (
        "Роль client должна присутствовать в сидированной базе"
    )
    return role


@pytest.fixture
async def operator_role(async_session: AsyncSession) -> RoleModel:
    """Возвращает сидированную роль оператора."""
    stmt = select(RoleModel).where(RoleModel.code == UserRole.OPERATOR)
    role = (await async_session.scalars(stmt)).first()
    assert role is not None, (
        "Роль operator должна присутствовать в сидированной базе"
    )
    return role


@pytest.fixture
async def supervisor_role(async_session: AsyncSession) -> RoleModel:
    """Возвращает сидированную роль супервизора."""
    stmt = select(RoleModel).where(RoleModel.code == UserRole.SUPERVISOR)
    role = (await async_session.scalars(stmt)).first()
    assert role is not None, (
        "Роль supervisor должна присутствовать в сидированной базе"
    )
    return role


@pytest.fixture
async def admin_role(async_session: AsyncSession) -> RoleModel:
    """Возвращает сидированную роль администратора."""
    stmt = select(RoleModel).where(RoleModel.code == UserRole.ADMIN)
    role = (await async_session.scalars(stmt)).first()
    assert role is not None, (
        "Роль admin должна присутствовать в сидированной базе"
    )
    return role


@pytest.fixture
async def support_line_l1(async_session: AsyncSession) -> SupportLineModel:
    """Возвращает сидированную линию поддержки L1."""
    stmt = select(SupportLineModel).where(SupportLineModel.code == "L1")
    line = (await async_session.scalars(stmt)).first()
    assert line is not None, (
        "Линия L1 должна присутствовать в сидированной базе"
    )
    return line
