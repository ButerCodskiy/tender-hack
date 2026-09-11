"""Интеграционные тесты эндпоинта загрузки документов базы знаний (POST /api/v1/kb/documents/upload)."""

import io
from unittest.mock import AsyncMock

from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import get_current_user, get_kb_service
from src.api.v1.kb import kb_router
from src.auth.models import RoleModel, UserModel
from src.kb.schemas import DocumentUploadItemResponseSchema


async def test_upload_documents_endpoint_202_accepted() -> None:
    """Проверяет успешный прием файлов и возврат HTTP 202 Accepted со статусом uploaded."""
    app = FastAPI()
    app.include_router(kb_router, prefix="/api/v1")

    mock_service = AsyncMock()
    mock_service.register_uploaded_files.return_value = [
        DocumentUploadItemResponseSchema(
            doc_id="kb_doc_018e5f1b_sample",
            title="test_regulation.pdf",
            status="uploaded",
            message="Документ принят в очередь на разбор и индексацию",
        )
    ]
    mock_user = UserModel(
        id="018e5f1b-0000-0000-0000-000000000001",
        email="supervisor@test.ru",
        password_hash="fake",
        full_name="Тестовый Супервизор",
        role=RoleModel(id=3, code="supervisor", name="Руководитель"),
        is_active=True,
    )
    app.dependency_overrides[get_kb_service] = lambda: mock_service
    app.dependency_overrides[get_current_user] = lambda: mock_user

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        file_payload = {
            "files": (
                "test_regulation.pdf",
                io.BytesIO(b"%PDF-1.4 fake binary regulation content"),
                "application/pdf",
            )
        }
        response = await client.post(
            "/api/v1/kb/documents/upload",
            files=file_payload,
            data={"regime": "MOS_PORTAL"},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    item = data[0]
    assert item["doc_id"] == "kb_doc_018e5f1b_sample"
    assert item["title"] == "test_regulation.pdf"
    assert item["status"] == "uploaded"
    assert "принят в очередь" in item["message"]
    mock_service.register_uploaded_files.assert_called_once()
