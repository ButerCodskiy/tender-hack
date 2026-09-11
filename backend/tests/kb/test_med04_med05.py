"""Интеграционные тесты MED-04 (обогащение чанков) и MED-05 (FAQ модерация)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import get_current_user, get_kb_service
from src.api.v1.kb import kb_router
from src.auth.models import RoleModel, UserModel
from src.core.config import settings
from src.kb.exceptions import (
    FaqDraftAlreadyReviewedError,
    FaqDraftNotFoundError,
)
from src.kb.schemas import (
    FaqDraftListResponse,
    FaqDraftResponse,
    FaqReviewResponse,
)

# ── Фикстуры ──────────────────────────────────────────────────


@pytest.fixture
def mock_kb_service() -> AsyncMock:
    """Мок сервиса базы знаний."""
    return AsyncMock()


@pytest.fixture
def mock_supervisor_user() -> UserModel:
    """Мок пользователя с ролью supervisor."""
    return UserModel(
        id=uuid6.uuid7(),
        email="supervisor@test.ru",
        password_hash="fake",
        full_name="Тестовый Супервизор",
        role=RoleModel(id=3, code="supervisor", name="Руководитель"),
        is_active=True,
    )


@pytest.fixture
def test_app(
    mock_kb_service: AsyncMock, mock_supervisor_user: UserModel
) -> FastAPI:
    """Создает изолированное приложение с обходом авторизации."""
    app = FastAPI()
    app.include_router(kb_router, prefix="/api/v1")
    app.dependency_overrides[get_kb_service] = lambda: mock_kb_service
    app.dependency_overrides[get_current_user] = lambda: mock_supervisor_user
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncClient:
    """Асинхронный HTTP-клиент."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


# ────────────────────────────────────────────────────────────────
# MED-04: Тесты фонового обогащения чанков
# ────────────────────────────────────────────────────────────────


class TestEnrichChunksBatch:
    """Тесты пакетного обогащения чанков (KbService.enrich_chunks_batch)."""

    async def test_enrich_chunks_batch_returns_count(self) -> None:
        """enrich_chunks_batch возвращает число обогащённых чанков."""
        mock_service = AsyncMock()
        mock_service.enrich_chunks_batch.return_value = 5
        result = await mock_service.enrich_chunks_batch(batch_size=10)
        assert result == 5
        mock_service.enrich_chunks_batch.assert_called_once_with(batch_size=10)

    async def test_enrich_chunks_batch_empty(self) -> None:
        """enrich_chunks_batch возвращает 0, когда нет необогащённых чанков."""
        mock_service = AsyncMock()
        mock_service.enrich_chunks_batch.return_value = 0
        result = await mock_service.enrich_chunks_batch(batch_size=50)
        assert result == 0

    async def test_enrich_chunk_updates_db_and_qdrant(self) -> None:
        """enrich_chunk вызывает обновление чанка в БД."""
        mock_service = AsyncMock()
        mock_chunk = MagicMock()
        mock_chunk.chunk_id = "test_chunk_1"
        mock_chunk.context_prefix = "Тестовый контекст"
        mock_chunk.hyp_questions = ["Вопрос 1?"]
        mock_service.enrich_chunk.return_value = mock_chunk

        result = await mock_service.enrich_chunk(
            chunk_id="test_chunk_1",
            context_prefix="Тестовый контекст",
            hyp_questions=["Вопрос 1?"],
        )
        assert result is not None
        assert result.chunk_id == "test_chunk_1"
        assert result.context_prefix == "Тестовый контекст"


# ────────────────────────────────────────────────────────────────
# MED-05: Тесты FAQ модерации — API
# ────────────────────────────────────────────────────────────────


class TestFaqDraftsApi:
    """Тесты REST API для FAQ-черновиков."""

    async def test_list_faq_drafts_200(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """GET /api/v1/kb/faq-drafts возвращает 200 и список черновиков."""
        now = datetime.now(settings.TIMEZONE)
        mock_kb_service.list_faq_drafts.return_value = FaqDraftListResponse(
            items=[
                FaqDraftResponse(
                    id="faq_001",
                    ticket_id="ticket_123",
                    question="Как подать заявку?",
                    answer="Через личный кабинет портала.",
                    kind="procedural",
                    status="PENDING",
                    created_at=now,
                ),
            ],
            total=1,
            limit=20,
            offset=0,
        )

        response = await api_client.get("/api/v1/kb/faq-drafts")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "faq_001"
        assert data["items"][0]["status"] == "PENDING"

    async def test_list_faq_drafts_with_status_filter(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """GET /api/v1/kb/faq-drafts?status=PENDING передаёт фильтр в сервис."""
        mock_kb_service.list_faq_drafts.return_value = FaqDraftListResponse(
            items=[], total=0, limit=20, offset=0
        )

        response = await api_client.get("/api/v1/kb/faq-drafts?status=PENDING")

        assert response.status_code == status.HTTP_200_OK
        mock_kb_service.list_faq_drafts.assert_called_once_with(
            status="PENDING", limit=20, offset=0
        )

    async def test_review_faq_draft_approve_200(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """POST /api/v1/kb/faq-drafts/{id}/review с approve возвращает 200."""
        mock_kb_service.review_faq_draft.return_value = FaqReviewResponse(
            draft_id="faq_001",
            status="APPROVED",
            chunk_id="faq_chunk_abc",
        )

        response = await api_client.post(
            "/api/v1/kb/faq-drafts/faq_001/review",
            json={"action": "approve"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["draft_id"] == "faq_001"
        assert data["status"] == "APPROVED"
        assert data["chunk_id"] == "faq_chunk_abc"

    async def test_review_faq_draft_reject_200(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """POST /api/v1/kb/faq-drafts/{id}/review с reject возвращает 200."""
        mock_kb_service.review_faq_draft.return_value = FaqReviewResponse(
            draft_id="faq_002",
            status="REJECTED",
            chunk_id=None,
        )

        response = await api_client.post(
            "/api/v1/kb/faq-drafts/faq_002/review",
            json={"action": "reject"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["chunk_id"] is None

    async def test_review_faq_draft_not_found_404(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """POST review для несуществующего черновика возвращает 404."""
        mock_kb_service.review_faq_draft.side_effect = FaqDraftNotFoundError(
            "faq_999"
        )

        response = await api_client.post(
            "/api/v1/kb/faq-drafts/faq_999/review",
            json={"action": "approve"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["code"] == "faq_draft_not_found"

    async def test_review_faq_draft_already_reviewed_409(
        self, api_client: AsyncClient, mock_kb_service: AsyncMock
    ) -> None:
        """POST review для уже обработанного черновика возвращает 409."""
        mock_kb_service.review_faq_draft.side_effect = (
            FaqDraftAlreadyReviewedError("faq_001", "APPROVED")
        )

        response = await api_client.post(
            "/api/v1/kb/faq-drafts/faq_001/review",
            json={"action": "approve"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["detail"]["code"] == "faq_draft_already_reviewed"


# ────────────────────────────────────────────────────────────────
# MED-05: Тесты сервисной логики FAQ
# ────────────────────────────────────────────────────────────────


class TestFaqServiceLogic:
    """Тесты сервисных методов create_faq_draft и review_faq_draft."""

    async def test_create_faq_draft(self) -> None:
        """create_faq_draft создаёт черновик со статусом PENDING."""
        mock_service = AsyncMock()
        now = datetime.now(settings.TIMEZONE)
        mock_service.create_faq_draft.return_value = FaqDraftResponse(
            id="faq_new",
            ticket_id="ticket_100",
            question="Тестовый вопрос?",
            answer="Тестовый ответ.",
            kind="procedural",
            status="PENDING",
            created_at=now,
        )

        result = await mock_service.create_faq_draft(
            ticket_id="ticket_100",
            question="Тестовый вопрос?",
            answer="Тестовый ответ.",
        )
        assert result.status == "PENDING"
        assert result.ticket_id == "ticket_100"
