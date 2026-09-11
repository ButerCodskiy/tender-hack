"""Корневой маршрутизатор API версии 1."""

from fastapi import APIRouter

from src.api.v1.auth import router as auth_router
from src.api.v1.chat import router as chat_router
from src.api.v1.kb import router as kb_router
from src.api.v1.operators import router as operators_router

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(operators_router)
router.include_router(kb_router)
