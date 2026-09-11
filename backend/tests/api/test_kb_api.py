"""Интеграционные и модульные тесты REST API реестра базы знаний (HIGH-07)."""

from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_kb_service
from src.api.v1.kb import kb_router
from src.auth.models import RoleModel, UserModel
from src.core.config import settings
from src.kb.exceptions import DocumentNotFoundError, NodeNotFoundError
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel
from src.kb.repository import KbRepository
from src.kb.schemas import (
    KbDocumentDeleteResponse,
    KbDocumentListResponse,
    KbDocumentResponse,
    KbDocumentStatusResponse,
    KbNodeResponse,
    KbNodeUpdateRequest,
)
from src.kb.service import KbService


@pytest.fixture
def mock_kb_service() -> AsyncMock:
    """Создает мок сервиса базы знаний для тестирования контроллера."""
    return AsyncMock(spec=KbService)


@pytest.fixture
def mock_supervisor_user() -> UserModel:
    """Создает мок пользователя с ролью supervisor для тестов KB API."""
    import uuid6

    return UserModel(
        id=uuid6.uuid7(),
        email="supervisor@mos.ru",
        password_hash="fake",
        full_name="Тестовый Супервизор",
        role=RoleModel(id=3, code="supervisor", name="Руководитель"),
        is_active=True,
    )


@pytest.fixture
def test_app(
    mock_kb_service: AsyncMock, mock_supervisor_user: UserModel
) -> FastAPI:
    """Создает изолированное приложение FastAPI с переопределенным KbService и авторизацией."""
    app = FastAPI()
    app.include_router(kb_router, prefix="/api/v1")
    app.dependency_overrides[get_kb_service] = lambda: mock_kb_service
    app.dependency_overrides[get_current_user] = lambda: mock_supervisor_user
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncClient:
    """Предоставляет асинхронный HTTP-клиент."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


# =====================================================================
# 1. Тесты эндпоинта GET /api/v1/kb/documents
# =====================================================================


async def test_list_documents_endpoint_success(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет получение реестра документов с пагинацией и фильтрами."""
    now = datetime.now(settings.TIMEZONE)
    mock_kb_service.list_documents.return_value = KbDocumentListResponse(
        items=[
            KbDocumentResponse(
                doc_id="kb_doc_1",
                title="Регламент 1",
                regime="MOS_PORTAL",
                edition_date=date(2026, 1, 1),
                status="indexed",
                error_message=None,
                source_url=None,
                created_at=now,
                updated_at=now,
            )
        ],
        total=1,
        limit=20,
        offset=0,
    )

    response = await api_client.get(
        "/api/v1/kb/documents",
        params={
            "regime": "MOS_PORTAL",
            "status": "indexed",
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 1
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert len(data["items"]) == 1
    assert data["items"][0]["doc_id"] == "kb_doc_1"
    assert data["items"][0]["status"] == "indexed"

    mock_kb_service.list_documents.assert_awaited_once_with(
        regime="MOS_PORTAL", status="indexed", limit=20, offset=0
    )


async def test_list_documents_endpoint_validation_errors(
    api_client: AsyncClient,
) -> None:
    """Проверяет возврат ошибки 422 при некорректных параметрах пагинации."""
    # limit < 1
    response = await api_client.get(
        "/api/v1/kb/documents", params={"limit": 0}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # limit > 100
    response = await api_client.get(
        "/api/v1/kb/documents", params={"limit": 101}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # offset < 0
    response = await api_client.get(
        "/api/v1/kb/documents", params={"offset": -1}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# =====================================================================
# 2. Тесты эндпоинта GET /api/v1/kb/documents/{doc_id}/status
# =====================================================================


async def test_get_document_status_endpoint_success(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет успешное получение статуса документа и количества чанков."""
    now = datetime.now(settings.TIMEZONE)
    mock_kb_service.get_document_status.return_value = (
        KbDocumentStatusResponse(
            doc_id="kb_doc_100",
            status="indexing",
            error_message=None,
            chunks_count=42,
            updated_at=now,
        )
    )

    response = await api_client.get("/api/v1/kb/documents/kb_doc_100/status")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["doc_id"] == "kb_doc_100"
    assert data["status"] == "indexing"
    assert data["chunks_count"] == 42
    mock_kb_service.get_document_status.assert_awaited_once_with("kb_doc_100")


async def test_get_document_status_endpoint_not_found(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет возврат 404 при отсутствии документа."""
    mock_kb_service.get_document_status.side_effect = DocumentNotFoundError(
        "kb_doc_missing"
    )

    response = await api_client.get(
        "/api/v1/kb/documents/kb_doc_missing/status"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error = response.json()
    assert error["detail"]["code"] == "document_not_found"
    assert "kb_doc_missing" in error["detail"]["message"]


# =====================================================================
# 3. Тесты эндпоинта DELETE /api/v1/kb/documents/{doc_id}
# =====================================================================


async def test_delete_document_endpoint_success(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет успешный запрос на удаление документа."""
    mock_kb_service.delete_document.return_value = KbDocumentDeleteResponse(
        deleted=True, doc_id="kb_doc_to_delete"
    )

    response = await api_client.delete("/api/v1/kb/documents/kb_doc_to_delete")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["deleted"] is True
    assert data["doc_id"] == "kb_doc_to_delete"
    mock_kb_service.delete_document.assert_awaited_once_with(
        "kb_doc_to_delete"
    )


async def test_delete_document_endpoint_not_found(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет возврат 404 при удалении несуществующего документа."""
    mock_kb_service.delete_document.side_effect = DocumentNotFoundError(
        "kb_doc_nonexistent"
    )

    response = await api_client.delete(
        "/api/v1/kb/documents/kb_doc_nonexistent"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error = response.json()
    assert error["detail"]["code"] == "document_not_found"
    assert "kb_doc_nonexistent" in error["detail"]["message"]


# =====================================================================
# 4. Тесты эндпоинта PATCH /api/v1/kb/nodes/{node_id}
# =====================================================================


async def test_patch_node_endpoint_success(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет успешную точечную модификацию заголовка и пути узла."""
    now = datetime.now(settings.TIMEZONE)
    mock_kb_service.update_node.return_value = KbNodeResponse(
        node_id="node_123",
        doc_id="kb_doc_1",
        parent_node_id=None,
        level="section",
        section_path="Раздел 1 / Новая статья",
        article_no="1",
        part_no=None,
        title="Новый заголовок",
        full_content="Текст узла",
        table_md=None,
        token_count=15,
        created_at=now,
    )

    response = await api_client.patch(
        "/api/v1/kb/nodes/node_123",
        json={
            "title": "Новый заголовок",
            "section_path": "Раздел 1 / Новая статья",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "node_123"
    assert data["title"] == "Новый заголовок"
    assert data["section_path"] == "Раздел 1 / Новая статья"
    mock_kb_service.update_node.assert_awaited_once()


async def test_patch_node_endpoint_not_found(
    api_client: AsyncClient, mock_kb_service: AsyncMock
) -> None:
    """Проверяет возврат 404 при редактировании несуществующего узла."""
    mock_kb_service.update_node.side_effect = NodeNotFoundError("node_missing")

    response = await api_client.patch(
        "/api/v1/kb/nodes/node_missing",
        json={"title": "Заголовок"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error = response.json()
    assert error["detail"]["code"] == "node_not_found"
    assert "node_missing" in error["detail"]["message"]


# =====================================================================
# 5. Модульные тесты сервисного слоя KbService (с моками)
# =====================================================================


async def test_service_unit_list_documents() -> None:
    """Проверяет маппинг и вызов list_documents в KbService."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    service = KbService(repo=mock_repo, session=mock_session)

    now = datetime.now(settings.TIMEZONE)
    mock_doc = KbDocumentModel(
        doc_id="doc_u1",
        title="Тестовый регламент",
        regime="MOS_PORTAL",
        edition_date=date(2026, 1, 1),
        status="indexed",
        error_message=None,
        source_url=None,
        created_at=now,
        updated_at=now,
    )
    mock_repo.list_documents.return_value = ([mock_doc], 1)

    result = await service.list_documents(
        regime="MOS_PORTAL", status="indexed", limit=10, offset=0
    )
    assert result.total == 1
    assert result.limit == 10
    assert result.offset == 0
    assert len(result.items) == 1
    assert result.items[0].doc_id == "doc_u1"
    mock_repo.list_documents.assert_awaited_once_with(
        skip=0, limit=10, regime="MOS_PORTAL", status="indexed"
    )


async def test_service_unit_get_document_status_success() -> None:
    """Проверяет агрегацию статуса и подсчета чанков."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    service = KbService(repo=mock_repo, session=mock_session)

    now = datetime.now(settings.TIMEZONE)
    mock_doc = KbDocumentModel(
        doc_id="doc_u2",
        title="Тест",
        status="indexing",
        error_message=None,
        updated_at=now,
    )
    mock_repo.get_document_status_info.return_value = (mock_doc, 8)

    status_resp = await service.get_document_status("doc_u2")
    assert status_resp.doc_id == "doc_u2"
    assert status_resp.status == "indexing"
    assert status_resp.chunks_count == 8


async def test_service_unit_get_document_status_not_found() -> None:
    """Проверяет выброс DocumentNotFoundError при отсутствии документа."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    service = KbService(repo=mock_repo, session=mock_session)

    mock_repo.get_document_status_info.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await service.get_document_status("doc_missing")


async def test_service_unit_delete_document_success() -> None:
    """Проверяет двухфазное удаление Qdrant -> PostgreSQL с коммитом."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_qdrant = AsyncMock()
    service = KbService(
        repo=mock_repo, session=mock_session, qdrant_client=mock_qdrant
    )

    mock_doc = KbDocumentModel(
        doc_id="doc_to_del", title="T", status="indexed"
    )
    mock_repo.get_document_by_id.return_value = mock_doc
    mock_repo.delete_document.return_value = True

    del_resp = await service.delete_document("doc_to_del")
    assert del_resp.deleted is True
    assert del_resp.doc_id == "doc_to_del"

    mock_qdrant.delete.assert_awaited_once()
    mock_repo.delete_document.assert_awaited_once_with("doc_to_del")
    mock_session.commit.assert_awaited_once()


async def test_service_unit_delete_document_not_found() -> None:
    """Проверяет DocumentNotFoundError при удалении несуществующего документа."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_qdrant = AsyncMock()
    service = KbService(
        repo=mock_repo, session=mock_session, qdrant_client=mock_qdrant
    )

    mock_repo.get_document_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await service.delete_document("doc_absent")

    mock_qdrant.delete.assert_not_called()
    mock_repo.delete_document.assert_not_called()


async def test_service_unit_delete_document_qdrant_failure_rollback() -> None:
    """Проверяет откат транзакции БД при сбое удаления точек в Qdrant."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_qdrant = AsyncMock()
    mock_qdrant.delete.side_effect = RuntimeError("Qdrant unavailable")
    service = KbService(
        repo=mock_repo, session=mock_session, qdrant_client=mock_qdrant
    )

    mock_doc = KbDocumentModel(
        doc_id="doc_fail_del", title="T", status="indexed"
    )
    mock_repo.get_document_by_id.return_value = mock_doc

    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        await service.delete_document("doc_fail_del")

    mock_session.rollback.assert_awaited_once()
    mock_repo.delete_document.assert_not_called()


async def test_service_unit_update_node_success() -> None:
    """Проверяет обновление узла и синхронизацию payload в Qdrant."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_qdrant = AsyncMock()
    service = KbService(
        repo=mock_repo, session=mock_session, qdrant_client=mock_qdrant
    )

    now = datetime.now(settings.TIMEZONE)
    mock_node = KbNodeModel(
        node_id="n_1",
        doc_id="d_1",
        level="article",
        section_path="Старый",
        title="Старый заголовок",
        full_content="Текст",
        token_count=10,
        created_at=now,
    )
    mock_repo.get_node_by_id.return_value = mock_node
    mock_updated = KbNodeModel(
        node_id="n_1",
        doc_id="d_1",
        level="article",
        section_path="Новый",
        title="Новый заголовок",
        full_content="Текст",
        token_count=10,
        created_at=now,
    )
    mock_repo.update_node.return_value = mock_updated

    resp = await service.update_node(
        "n_1",
        KbNodeUpdateRequest(title="Новый заголовок", section_path="Новый"),
    )
    assert resp.title == "Новый заголовок"
    assert resp.section_path == "Новый"

    mock_qdrant.set_payload.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


async def test_service_unit_update_node_not_found() -> None:
    """Проверяет NodeNotFoundError при попытке обновления несуществующего узла."""
    mock_repo = AsyncMock(spec=KbRepository)
    mock_session = AsyncMock(spec=AsyncSession)
    service = KbService(repo=mock_repo, session=mock_session)

    mock_repo.get_node_by_id.return_value = None

    with pytest.raises(NodeNotFoundError):
        await service.update_node("n_missing", KbNodeUpdateRequest(title="X"))


# =====================================================================
# 6. Интеграционные тесты сервисного слоя и репозитория (DB + Qdrant mock)
# =====================================================================


async def test_service_list_documents_and_filtering(
    async_session: AsyncSession,
) -> None:
    """Проверяет корректность фильтрации, пагинации и подсчета total в KbService."""
    repo = KbRepository(session=async_session)
    service = KbService(repo=repo, session=async_session, qdrant_client=None)

    # Создаем 3 тестовых документа с разными режимами и статусами
    doc1 = KbDocumentModel(
        doc_id="doc_test_1",
        title="Документ 1",
        regime="MOS_PORTAL",
        status="indexed",
    )
    doc2 = KbDocumentModel(
        doc_id="doc_test_2",
        title="Документ 2",
        regime="MOS_PORTAL",
        status="uploaded",
    )
    doc3 = KbDocumentModel(
        doc_id="doc_test_3",
        title="Документ 3",
        regime="LAW_44",
        status="indexed",
    )
    async_session.add_all([doc1, doc2, doc3])
    await async_session.flush()

    # Запрос без фильтров
    res_all = await service.list_documents(limit=10, offset=0)
    assert res_all.total == 3
    assert len(res_all.items) == 3

    # Фильтр по regime
    res_regime = await service.list_documents(
        regime="MOS_PORTAL", limit=10, offset=0
    )
    assert res_regime.total == 2
    assert {d.doc_id for d in res_regime.items} == {"doc_test_1", "doc_test_2"}

    # Фильтр по regime и status
    res_filtered = await service.list_documents(
        regime="MOS_PORTAL", status="indexed", limit=10, offset=0
    )
    assert res_filtered.total == 1
    assert res_filtered.items[0].doc_id == "doc_test_1"

    # Пагинация
    res_paged = await service.list_documents(limit=1, offset=1)
    assert res_paged.total == 3
    assert len(res_paged.items) == 1


async def test_service_get_document_status_and_chunks_count(
    async_session: AsyncSession,
) -> None:
    """Проверяет агрегацию количества чанков в статусе документа."""
    repo = KbRepository(session=async_session)
    service = KbService(repo=repo, session=async_session, qdrant_client=None)

    doc = KbDocumentModel(
        doc_id="doc_with_chunks",
        title="Документ с чанками",
        regime="MOS_PORTAL",
        status="indexing",
    )
    node = KbNodeModel(
        node_id="node_chunks_1",
        doc_id=doc.doc_id,
        level="section",
        section_path="Раздел 1",
        title="Заголовок",
        full_content="Контент",
        token_count=10,
    )
    chunk1 = KbChunkModel(
        chunk_id="chunk_1",
        node_id=node.node_id,
        text="Фрагмент 1",
        hyp_questions=[],
    )
    chunk2 = KbChunkModel(
        chunk_id="chunk_2",
        node_id=node.node_id,
        text="Фрагмент 2",
        hyp_questions=[],
    )
    async_session.add_all([doc, node, chunk1, chunk2])
    await async_session.flush()

    status_resp = await service.get_document_status(doc.doc_id)
    assert status_resp.doc_id == doc.doc_id
    assert status_resp.status == "indexing"
    assert status_resp.chunks_count == 2

    # Несуществующий документ
    with pytest.raises(DocumentNotFoundError):
        await service.get_document_status("nonexistent_doc")


async def test_service_delete_document_two_phase_success(
    async_session: AsyncSession,
) -> None:
    """Проверяет удаление из Qdrant и каскадное удаление из PostgreSQL."""
    mock_qdrant = AsyncMock()
    repo = KbRepository(session=async_session)
    service = KbService(
        repo=repo, session=async_session, qdrant_client=mock_qdrant
    )

    doc = KbDocumentModel(
        doc_id="doc_to_cascade_del",
        title="Документ на удаление",
        regime="MOS_PORTAL",
        status="indexed",
    )
    node = KbNodeModel(
        node_id="node_to_del",
        doc_id=doc.doc_id,
        level="section",
        section_path="Раздел 1",
        title="Заголовок",
        full_content="Контент",
        token_count=5,
    )
    chunk = KbChunkModel(
        chunk_id="chunk_to_del",
        node_id=node.node_id,
        text="Фрагмент",
        hyp_questions=[],
    )
    async_session.add_all([doc, node, chunk])
    await async_session.commit()

    del_resp = await service.delete_document(doc.doc_id)
    assert del_resp.deleted is True
    assert del_resp.doc_id == doc.doc_id

    # Проверяем вызов очистки в Qdrant
    mock_qdrant.delete.assert_awaited_once()

    # Проверяем, что в БД документ и связанные сущности удалены
    assert await repo.get_document_by_id(doc.doc_id) is None
    assert await repo.get_node_by_id(node.node_id) is None


async def test_service_delete_document_qdrant_failure_rollback(
    async_session: AsyncSession,
) -> None:
    """Проверяет откат транзакции PostgreSQL, если Qdrant выбросил ошибку."""
    mock_qdrant = AsyncMock()
    mock_qdrant.delete.side_effect = RuntimeError("Qdrant connection timeout")

    repo = KbRepository(session=async_session)
    service = KbService(
        repo=repo, session=async_session, qdrant_client=mock_qdrant
    )

    doc = KbDocumentModel(
        doc_id="doc_rollback_test",
        title="Документ с защитой от сбоя векторов",
        regime="MOS_PORTAL",
        status="indexed",
    )
    async_session.add(doc)
    await async_session.commit()

    with pytest.raises(RuntimeError, match="Qdrant connection timeout"):
        await service.delete_document(doc.doc_id)

    # Документ обязан сохраниться в базе данных
    saved_doc = await repo.get_document_by_id(doc.doc_id)
    assert saved_doc is not None
    assert saved_doc.doc_id == doc.doc_id


async def test_service_update_node_syncs_qdrant(
    async_session: AsyncSession,
) -> None:
    """Проверяет обновление узла в PostgreSQL и вызов set_payload в Qdrant."""
    mock_qdrant = AsyncMock()
    repo = KbRepository(session=async_session)
    service = KbService(
        repo=repo, session=async_session, qdrant_client=mock_qdrant
    )

    doc = KbDocumentModel(
        doc_id="doc_for_node",
        title="Документ узла",
        regime="MOS_PORTAL",
        status="indexed",
    )
    node = KbNodeModel(
        node_id="node_edit_test",
        doc_id=doc.doc_id,
        level="section",
        section_path="Старый путь",
        title="Старый заголовок",
        full_content="Контент",
        token_count=12,
    )
    async_session.add_all([doc, node])
    await async_session.commit()

    updated = await service.update_node(
        node_id=node.node_id,
        data=KbNodeUpdateRequest(
            title="Обновленный заголовок",
            section_path="Новый / Путь",
        ),
    )

    assert updated.title == "Обновленный заголовок"
    assert updated.section_path == "Новый / Путь"

    # Проверяем обновление в Qdrant
    mock_qdrant.set_payload.assert_awaited_once()
    call_kwargs = mock_qdrant.set_payload.call_args.kwargs
    assert call_kwargs["payload"] == {
        "title": "Обновленный заголовок",
        "section_path": "Новый / Путь",
    }
