"""Комплексные тесты проверки ролевой модели (RBAC) и разграничения прав доступа (HIGH-13)."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    AccessDeniedException,
    RoleChecker,
    get_auth_service,
    get_chat_service,
    get_kb_service,
    get_operator_service,
)
from src.api.v1.router import router as api_v1_router
from src.auth.models import RoleModel, UserModel, UserRole
from src.auth.service import AuthService
from src.chat.schemas import ChatStateResponseSchema
from src.chat.service import ChatService
from src.kb.schemas import (
    DocumentUploadItemResponseSchema,
    KbDocumentDeleteResponse,
    KbDocumentListResponse,
    KbNodeResponse,
)
from src.kb.service import KbService
from src.operators.schemas import OperatorProfileResponseSchema
from src.operators.service import OperatorService

# =====================================================================
# Вспомогательные фабрики пользователей
# =====================================================================


def make_user(role_code: str, email: str | None = None) -> UserModel:
    """Создает тестового пользователя с заданной ролью."""
    uid = uuid6.uuid7()
    role_id_map = {"client": 1, "operator": 2, "supervisor": 3, "admin": 4}
    return UserModel(
        id=uid,
        email=email or f"{role_code}_{uid.hex[:6]}@example.com",
        password_hash="hashed_pw",
        full_name=f"Test {role_code.capitalize()}",
        role=RoleModel(
            id=role_id_map.get(role_code, 99),
            code=role_code,
            name=role_code.capitalize(),
        ),
        is_active=True,
    )


# =====================================================================
# 1. Модульные тесты ядра RBAC: AccessDeniedException и RoleChecker
# =====================================================================


def test_access_denied_exception_format() -> None:
    """Проверяет структуру ошибки 403 согласно ErrorResponseSchema API_SPECIFICATION §1.3."""
    exc = AccessDeniedException("Кастомное сообщение")
    assert exc.status_code == status.HTTP_403_FORBIDDEN
    assert isinstance(exc.detail, dict)
    assert exc.detail["code"] == "access_denied"
    assert exc.detail["message"] == "Кастомное сообщение"


def test_role_checker_allowed_user() -> None:
    """Проверяет успешное прохождение пользователя с разрешенной ролью."""
    checker = RoleChecker([UserRole.CLIENT])
    client_user = make_user("client")
    assert checker._check(client_user) is client_user

    op_checker = RoleChecker([UserRole.OPERATOR, UserRole.ADMIN])
    op_user = make_user("operator")
    admin_user = make_user("admin")
    assert op_checker._check(op_user) is op_user
    assert op_checker._check(admin_user) is admin_user


def test_role_checker_forbidden_user_raises_403() -> None:
    """Проверяет выброс 403 Forbidden при несоответствии роли."""
    checker = RoleChecker(
        [UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN]
    )
    client_user = make_user("client")

    with pytest.raises(AccessDeniedException) as exc_info:
        checker._check(client_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail["code"] == "access_denied"
    assert (
        "Доступ разрешен только операторам" in exc_info.value.detail["message"]
    )


def test_role_checker_user_without_role_safe() -> None:
    """Проверяет устойчивость к отсутствию связи role (защита от MissingGreenlet)."""
    checker = RoleChecker([UserRole.CLIENT])
    user_without_role = UserModel(
        id=uuid6.uuid7(),
        email="norole@example.com",
        password_hash="hashed_pw",
        is_active=True,
    )
    # Симулируем незагруженную связь (role отсутствует в __dict__)
    if "role" in user_without_role.__dict__:
        del user_without_role.__dict__["role"]

    with pytest.raises(AccessDeniedException) as exc_info:
        checker._check(user_without_role)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail["code"] == "access_denied"


# =====================================================================
# 2. Фикстуры интеграционного тестирования маршрутов
# =====================================================================


@pytest.fixture
def mock_auth_service() -> AsyncMock:
    """Создает мок сервиса аутентификации с динамическим возвратом пользователя по токену."""
    service = AsyncMock(spec=AuthService)

    async def _get_user_by_token(token: str, **kwargs) -> UserModel:
        if token == "token_client":
            return make_user("client")
        elif token == "token_operator":
            return make_user("operator")
        elif token == "token_supervisor":
            return make_user("supervisor")
        elif token == "token_admin":
            return make_user("admin")
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "token_expired",
                "message": "Токен недействителен",
            },
        )

    service.get_user_by_token.side_effect = _get_user_by_token
    return service


@pytest.fixture
def mock_chat_service() -> AsyncMock:
    """Создает мок ChatService."""
    service = AsyncMock(spec=ChatService)
    service.get_chat_state.return_value = ChatStateResponseSchema(
        chat_id=uuid6.uuid7(),
        active_ticket=None,
        messages=[],
        can_escalate=False,
        can_cancel=False,
        can_feedback=False,
        feedback_ticket_id=None,
    )

    async def _dummy_chat_stream(*args, **kwargs) -> AsyncGenerator[str, None]:
        yield 'event: new_message\ndata: {"ok": true}\n\n'

    service.stream_chat_events = _dummy_chat_stream
    service.process_client_message = _dummy_chat_stream
    return service


@pytest.fixture
def mock_kb_service() -> AsyncMock:
    """Создает мок KbService."""
    from datetime import datetime

    from src.core.config import settings

    service = AsyncMock(spec=KbService)
    service.list_documents.return_value = KbDocumentListResponse(
        total=0, offset=0, limit=20, items=[]
    )
    service.register_uploaded_files.return_value = [
        DocumentUploadItemResponseSchema(
            doc_id="test_doc",
            title="test.pdf",
            status="uploaded",
            message="Файл принят",
        )
    ]
    service.delete_document.return_value = KbDocumentDeleteResponse(
        doc_id="test_doc",
        deleted=True,
    )
    service.update_node.return_value = KbNodeResponse(
        node_id="test_node",
        doc_id="test_doc",
        level="section",
        section_path="1",
        title="Updated Node",
        full_content="Content",
        created_at=datetime.now(settings.TIMEZONE),
    )
    return service


@pytest.fixture
def mock_operator_service() -> AsyncMock:
    """Создает мок OperatorService."""
    service = AsyncMock(spec=OperatorService)
    uid = uuid6.uuid7()
    service.get_profile.return_value = OperatorProfileResponseSchema(
        user_id=uid,
        full_name="Оператор Тест",
        line_id=1,
        line_code="L1",
        shift_status="active",
        max_slots=3,
        active_slots_count=0,
    )
    return service


@pytest.fixture
def test_app(
    mock_auth_service: AsyncMock,
    mock_chat_service: AsyncMock,
    mock_kb_service: AsyncMock,
    mock_operator_service: AsyncMock,
) -> FastAPI:
    """Создает изолированное приложение FastAPI с полным набором роутеров v1."""
    app = FastAPI()
    app.include_router(api_v1_router)

    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    app.dependency_overrides[get_kb_service] = lambda: mock_kb_service
    app.dependency_overrides[get_operator_service] = lambda: (
        mock_operator_service
    )

    # Добавляем тестовый эндпоинт в analytics для проверки защиты уровня роутера
    from src.api.v1.analytics import router as analytics_router

    @analytics_router.get("/test-endpoint")
    async def analytics_test_endpoint():
        return {"status": "analytics_ok"}

    return app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Предоставляет HTTP-клиент."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =====================================================================
# 3. Интеграционные тесты матрицы доступа RBAC
# =====================================================================


async def test_unauthorized_requests_return_401(client: AsyncClient) -> None:
    """Проверяет возврат 401 при отсутствии токена авторизации на закрытых маршрутах."""
    endpoints = [
        ("GET", "/api/v1/chat"),
        ("GET", "/api/v1/chat/events"),
        ("GET", "/api/v1/kb/documents"),
        ("POST", "/api/v1/kb/documents/upload"),
        ("GET", "/api/v1/operators/me/shift"),
        ("GET", "/api/v1/analytics/test-endpoint"),
    ]
    for method, path in endpoints:
        resp = await client.request(method, path)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Failed for {method} {path}"
        )
        assert resp.json()["detail"]["code"] == "not_authenticated"


async def test_client_chat_strictly_for_client_role(
    client: AsyncClient,
) -> None:
    """Проверяет, что маршруты /chat доступны клиенту и возвращают 403 для оператора/супервизора/админа."""
    # 1. Клиент — успешный доступ
    resp = await client.get(
        "/api/v1/chat", headers={"Authorization": "Bearer token_client"}
    )
    assert resp.status_code == status.HTTP_200_OK

    # 2. Оператор — отказ в доступе (403 access_denied)
    resp = await client.get(
        "/api/v1/chat", headers={"Authorization": "Bearer token_operator"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # 3. Супервизор — отказ в доступе (403 access_denied)
    resp = await client.get(
        "/api/v1/chat", headers={"Authorization": "Bearer token_supervisor"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # 4. Администратор — отказ в доступе (403 access_denied)
    resp = await client.get(
        "/api/v1/chat", headers={"Authorization": "Bearer token_admin"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"


async def test_client_chat_events_sse_rbac(client: AsyncClient) -> None:
    """Проверяет RBAC для SSE-потока клиента через query-параметр ?token=."""
    # Клиент — 200 OK text/event-stream
    resp = await client.get("/api/v1/chat/events?token=token_client")
    assert resp.status_code == status.HTTP_200_OK

    # Оператор — 403 Forbidden access_denied
    resp = await client.get("/api/v1/chat/events?token=token_operator")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"


async def test_kb_read_endpoints_allow_staff_deny_client(
    client: AsyncClient,
) -> None:
    """Проверяет чтение KB: доступно operator, supervisor, admin; запрещено client."""
    # Клиент — 403
    resp = await client.get(
        "/api/v1/kb/documents",
        headers={"Authorization": "Bearer token_client"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # Оператор — 200
    resp = await client.get(
        "/api/v1/kb/documents",
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp.status_code == status.HTTP_200_OK

    # Супервизор — 200
    resp = await client.get(
        "/api/v1/kb/documents",
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp.status_code == status.HTTP_200_OK

    # Администратор — 200
    resp = await client.get(
        "/api/v1/kb/documents", headers={"Authorization": "Bearer token_admin"}
    )
    assert resp.status_code == status.HTTP_200_OK


async def test_kb_mutation_endpoints_strictly_supervisor_admin(
    client: AsyncClient,
) -> None:
    """Проверяет мутации KB (upload, delete, patch): строго supervisor и admin; отказ operator и client."""
    # 1. POST /upload: клиент и оператор получают 403
    files = {"files": ("test.pdf", b"test content", "application/pdf")}
    resp_client = await client.post(
        "/api/v1/kb/documents/upload",
        files=files,
        headers={"Authorization": "Bearer token_client"},
    )
    assert resp_client.status_code == status.HTTP_403_FORBIDDEN
    assert resp_client.json()["detail"]["code"] == "access_denied"

    files = {"files": ("test.pdf", b"test content", "application/pdf")}
    resp_op = await client.post(
        "/api/v1/kb/documents/upload",
        files=files,
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp_op.status_code == status.HTTP_403_FORBIDDEN
    assert resp_op.json()["detail"]["code"] == "access_denied"

    # Супервизор и админ получают 202
    files = {"files": ("test.pdf", b"test content", "application/pdf")}
    resp_sup = await client.post(
        "/api/v1/kb/documents/upload",
        files=files,
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp_sup.status_code == status.HTTP_202_ACCEPTED

    files = {"files": ("test.pdf", b"test content", "application/pdf")}
    resp_adm = await client.post(
        "/api/v1/kb/documents/upload",
        files=files,
        headers={"Authorization": "Bearer token_admin"},
    )
    assert resp_adm.status_code == status.HTTP_202_ACCEPTED

    # 2. DELETE /documents/{id}: оператор — 403, супервизор — 200
    resp_del_op = await client.delete(
        "/api/v1/kb/documents/test_doc",
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp_del_op.status_code == status.HTTP_403_FORBIDDEN
    assert resp_del_op.json()["detail"]["code"] == "access_denied"

    resp_del_sup = await client.delete(
        "/api/v1/kb/documents/test_doc",
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp_del_sup.status_code == status.HTTP_200_OK

    # 3. PATCH /nodes/{id}: оператор — 403, супервизор — 200
    resp_patch_op = await client.patch(
        "/api/v1/kb/nodes/test_node",
        json={"title": "New Title"},
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp_patch_op.status_code == status.HTTP_403_FORBIDDEN
    assert resp_patch_op.json()["detail"]["code"] == "access_denied"

    resp_patch_sup = await client.patch(
        "/api/v1/kb/nodes/test_node",
        json={"title": "New Title"},
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp_patch_sup.status_code == status.HTTP_200_OK


async def test_operators_endpoints_rbac(client: AsyncClient) -> None:
    """Проверяет эндпоинты операторов: доступно operator, supervisor, admin; запрещено client."""
    # Клиент — 403
    resp = await client.get(
        "/api/v1/operators/me/shift",
        headers={"Authorization": "Bearer token_client"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # Оператор — 200
    resp = await client.get(
        "/api/v1/operators/me/shift",
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp.status_code == status.HTTP_200_OK

    # Супервизор — 200
    resp = await client.get(
        "/api/v1/operators/me/shift",
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp.status_code == status.HTTP_200_OK

    # Админ — 200
    resp = await client.get(
        "/api/v1/operators/me/shift",
        headers={"Authorization": "Bearer token_admin"},
    )
    assert resp.status_code == status.HTTP_200_OK


async def test_analytics_router_level_rbac(client: AsyncClient) -> None:
    """Проверяет защиту контура аналитики на уровне роутера: доступно supervisor и admin; отказ client и operator."""
    # Клиент — 403
    resp = await client.get(
        "/api/v1/analytics/test-endpoint",
        headers={"Authorization": "Bearer token_client"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # Оператор — 403
    resp = await client.get(
        "/api/v1/analytics/test-endpoint",
        headers={"Authorization": "Bearer token_operator"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["detail"]["code"] == "access_denied"

    # Супервизор — 200
    resp = await client.get(
        "/api/v1/analytics/test-endpoint",
        headers={"Authorization": "Bearer token_supervisor"},
    )
    assert resp.status_code == status.HTTP_200_OK

    # Администратор — 200
    resp = await client.get(
        "/api/v1/analytics/test-endpoint",
        headers={"Authorization": "Bearer token_admin"},
    )
    assert resp.status_code == status.HTTP_200_OK
