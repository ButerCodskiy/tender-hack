"""Точка входа веб-приложения FastAPI (базовый скаффолдинг)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
