"""Точка входа веб-приложения FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import router as api_v1_router
from src.core.broker import broker
from src.core.config import settings
from src.db.database import async_session_maker, engine
from src.operators.service import OperatorService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управление жизненным циклом приложения: запуск и освобождение ресурсов."""
    # Единый пул соединений Redis для HTTP-обработчиков и воркеров Taskiq
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.redis = redis

    # Запуск брокера фоновых задач
    if not broker.is_worker_process:
        await broker.startup()

    # Аварийное восстановление очередей ожидания из PostgreSQL в Redis
    try:
        async with async_session_maker() as session:
            operator_service = OperatorService(session=session, redis=redis)
            await operator_service.recover_queued_tickets_from_db()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Не удалось выполнить восстановление очередей при старте: %s", exc
        )

    yield

    # Корректное завершение брокера задач
    if not broker.is_worker_process:
        await broker.shutdown()

    # Закрытие пулов соединений
    await redis.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Диагностический эндпоинт проверки работоспособности сервиса."""
    return {"status": "ok"}


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Корневой эндпоинт со ссылками на документацию и фронтенд."""
    return {
        "service": settings.PROJECT_NAME,
        "status": "online",
        "docs": "http://127.0.0.1:8000/docs",
        "frontend": "http://localhost:5173",
    }
