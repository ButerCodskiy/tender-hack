"""Глобальные фикстуры тестового окружения на базе Testcontainers.

Паттерн: session-scoped контейнер и engine по образцу microservices-shop/order-service,
полностью изолирующий тесты от локальной рабочей базы данных.
"""

import os
from collections.abc import AsyncGenerator, Generator

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from src.core.config import settings

# Если SSL_CERT_FILE указывает на директорию (баг в окружении Windows),
# удаляем его из окружения во избежание PermissionError в ssl/httpx
if "SSL_CERT_FILE" in os.environ and not os.path.isfile(
    os.environ["SSL_CERT_FILE"]
):
    os.environ.pop("SSL_CERT_FILE", None)

# Отключаем Ryuk (сервис очистки testcontainers), т.к. на Docker Desktop (Windows)
# он часто падает с ошибкой проброса портов
os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

# Запускаем контейнер до загрузки настроек и движка SQLAlchemy (если Docker доступен)
_pg_container = None
try:
    _pg_container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    _pg_container.start()
    os.environ["DB_HOST"] = _pg_container.get_container_host_ip()
    os.environ["DB_PORT"] = str(_pg_container.get_exposed_port(5432))
    os.environ["DB_USER"] = _pg_container.username
    os.environ["DB_PASS"] = _pg_container.password
    os.environ["DB_NAME"] = _pg_container.dbname
except Exception:
    _pg_container = None

from src.db.database import Base  # noqa: E402


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Останавливает контейнер PostgreSQL по завершении всей тестовой сессии."""
    if _pg_container is not None:
        _pg_container.stop()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Предоставляет инстанс контейнера PostgreSQL на время сессии."""
    if _pg_container is None:
        pytest.skip(
            "Docker / Testcontainers PostgreSQL недоступен в текущем окружении"
        )
    yield _pg_container


@pytest.fixture(scope="session")
async def async_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Создает асинхронный движок один раз на всю сессию тестов."""
    url = postgres_container.get_connection_url()
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


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
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Предоставляет асинхронный клиент Redis для тестов."""
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
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
