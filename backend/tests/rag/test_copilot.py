"""Тесты аналитической подсказки оператора AI Copilot (HIGH-04)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uuid6
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import RoleModel, UserModel
from src.chat.models import ChatModel, TicketModel, TicketStatus
from src.operators.models import (
    TicketCopilotSummaryModel,
)
from src.operators.repository import OperatorRepository
from src.operators.schemas import (
    CopilotSummaryResponseSchema,
)
from src.operators.service import OperatorService
from src.rag.copilot import (
    CopilotService,
    MockCopilotLlmClient,
)
from src.rag.qdrant_tickets import (
    RESOLVED_TICKETS_COLLECTION,
    SEED_RESOLVED_TICKETS,
    ensure_resolved_tickets_collection,
    search_similar_resolved_tickets,
)
from src.rag.schemas import CopilotLlmOutputSchema, CopilotPayloadSchema
from src.rag.tasks import generate_copilot_summary

# =========================================================================
# 1. Тесты схем Pydantic
# =========================================================================


def test_copilot_payload_schema_validation() -> None:
    """Проверяет валидацию полезной нагрузки очереди copilot_queue."""
    uid = uuid6.uuid7()
    valid = CopilotPayloadSchema(ticket_id=uid)
    assert valid.ticket_id == uid

    with pytest.raises(ValidationError):
        CopilotPayloadSchema(ticket_id="invalid-uuid")


def test_copilot_llm_output_schema() -> None:
    """Проверяет сериализацию и значения по умолчанию CopilotLlmOutputSchema."""
    output = CopilotLlmOutputSchema(
        summary="Проблема со входом",
        suggested_line_code="L2",
        suggested_response="Инструкция для входа",
        recommended_chunk_ids=["chunk_1"],
    )
    assert output.suggested_line_code == "L2"
    assert len(output.recommended_chunk_ids) == 1


# =========================================================================
# 2. Тесты эвристик и надежности MockCopilotLlmClient
# =========================================================================


@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l2_crypto_marker() -> None:
    """Проверяет авто-назначение линии L2 при обнаружении ошибки КриптоПро / ЭЦП."""
    client = MockCopilotLlmClient()
    result = await client.generate_copilot_summary(
        prompt="Клиент: Не подписывается протокол! Ошибка 0x80090016 в плагине КриптоПро",
        system_prompt="",
    )
    assert result.suggested_line_code == "L2"
    assert "0x80090016" in result.summary or "плагина ЭЦП" in result.summary
    assert "КриптоПро" in result.suggested_response


@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l1_regulation_marker() -> None:
    """Проверяет авто-назначение линии L1 при вопросе о регламенте и котировочных сессиях."""
    client = MockCopilotLlmClient()
    result = await client.generate_copilot_summary(
        prompt="Пользователь: В какой срок направляется протокол разногласий к котировочной сессии?",
        system_prompt="",
    )
    assert result.suggested_line_code == "L1"
    assert "протокол разногласий" in result.summary.lower()
    assert "3 рабочих дней" in result.suggested_response


@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l3_dispute_marker() -> None:
    """Проверяет авто-назначение линии L3 при маркерах спора / угрозе жалобы в ФАС."""
    client = MockCopilotLlmClient()
    result = await client.generate_copilot_summary(
        prompt="Заказчик грозит жалобой в ФАС и односторонним расторжением контракта!",
        system_prompt="",
    )
    assert result.suggested_line_code == "L3"
    assert "ФАС" in result.summary


@pytest.mark.asyncio
async def test_mock_copilot_llm_client_timeout_simulation() -> None:
    """Проверяет генерацию исключения при симуляции сбоя fail_times."""
    client = MockCopilotLlmClient(fail_times=1)
    with pytest.raises(TimeoutError):
        await client.generate_copilot_summary("Тестовый запрос", "")

    # Вторая попытка должна пройти успешно
    success = await client.generate_copilot_summary("Тестовый запрос", "")
    assert success.summary is not None


# =========================================================================
# 3. Тесты векторного хранилища прецедентов resolved_tickets
# =========================================================================


@pytest.mark.asyncio
async def test_qdrant_tickets_ensure_and_seed() -> None:
    """Проверяет создание коллекции и загрузку сид-корпуса прецедентов."""
    mock_client = AsyncMock()

    # Имитация отсутствия коллекции
    collections_res = MagicMock()
    collections_res.collections = []
    mock_client.get_collections.return_value = collections_res

    await ensure_resolved_tickets_collection(mock_client)

    mock_client.create_collection.assert_awaited_once()
    assert (
        mock_client.create_collection.await_args.kwargs["collection_name"]
        == RESOLVED_TICKETS_COLLECTION
    )
    mock_client.upsert.assert_awaited_once()
    points = mock_client.upsert.await_args.kwargs["points"]
    assert len(points) == len(SEED_RESOLVED_TICKETS)


@pytest.mark.asyncio
async def test_qdrant_tickets_search_mocked() -> None:
    """Проверяет маппинг результатов векторного поиска в SimilarTicketItemSchema."""
    mock_client = AsyncMock()

    # Коллекция уже существует
    collections_res = MagicMock()
    existing_c = MagicMock()
    existing_c.name = RESOLVED_TICKETS_COLLECTION
    collections_res.collections = [existing_c]
    mock_client.get_collections.return_value = collections_res

    # Имитация результата поиска от Qdrant
    scored_point = MagicMock()
    scored_point.id = "018e0000-0000-7000-8000-000000000001"
    scored_point.score = 0.9412
    scored_point.payload = {
        "ticket_id": "018e0000-0000-7000-8000-000000000001",
        "support_line": "L2",
        "user_query": "Ошибка 0x80090016 при подписании",
        "solution_text": "Переустановите плагин КриптоПро",
    }
    mock_client.search.return_value = [scored_point]
    mock_client.query_points.return_value = MagicMock(points=[scored_point])

    items = await search_similar_resolved_tickets(
        client=mock_client,
        query_text="У меня сбой 0x80090016",
        limit=3,
    )
    assert len(items) == 1
    assert items[0].ticket_id == "018e0000-0000-7000-8000-000000000001"
    assert items[0].support_line == "L2"
    assert items[0].similarity_score == 0.9412


@pytest.mark.asyncio
async def test_qdrant_tickets_graceful_degradation() -> None:
    """Проверяет возврат пустого списка при сбое или недоступности Qdrant."""
    # Случай 1: client is None
    res_none = await search_similar_resolved_tickets(None, "запрос")
    assert res_none == []

    # Случай 2: client бросает исключение сети
    mock_failing_client = AsyncMock()
    mock_failing_client.get_collections.side_effect = RuntimeError(
        "Qdrant connection refused"
    )

    res_fail = await search_similar_resolved_tickets(
        mock_failing_client, "запрос"
    )
    assert res_fail == []


# =========================================================================
# 4. Тесты сервиса CopilotService
# =========================================================================


@pytest.mark.asyncio
async def test_copilot_service_assembly() -> None:
    """Проверяет сборку полного объекта CopilotSummaryResponseSchema."""
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = MagicMock(
        collections=[MagicMock(name=RESOLVED_TICKETS_COLLECTION)]
    )
    mock_qdrant.query_points.return_value = MagicMock(points=[])
    mock_qdrant.search.return_value = []

    service = CopilotService(
        llm_client=MockCopilotLlmClient(), qdrant_client=mock_qdrant
    )

    messages = [
        {
            "sender": "client",
            "text": "Здравствуйте, как направить протокол разногласий?",
        },
        {"sender": "bot", "text": "Идет поиск регламента..."},
    ]

    summary = await service.build_copilot_summary(
        ticket_id=uuid6.uuid7(),
        messages=messages,
    )
    assert isinstance(summary, CopilotSummaryResponseSchema)
    assert summary.suggested_line_code == "L1"
    assert "протокол разногласий" in summary.summary.lower()
    assert summary.suggested_response is not None


# =========================================================================
# 5. Модульные тесты синхронизации АРМ оператора (Two-Way Race Condition)
# =========================================================================


@pytest.mark.asyncio
async def test_open_ticket_returns_existing_summary_unit() -> None:
    """Сценарий Б: open_ticket возвращает сохраненную подсказку из объекта тикета."""
    ticket_id = uuid6.uuid7()
    operator_id = uuid6.uuid7()

    mock_ticket = MagicMock(spec=TicketModel)
    mock_ticket.id = ticket_id
    mock_ticket.chat_id = uuid6.uuid7()
    mock_ticket.priority = "P1"
    mock_ticket.status = TicketStatus.IN_PROGRESS.value
    mock_ticket.line = MagicMock()
    mock_ticket.line.code = "L2"
    mock_ticket.transfer_comment = None
    mock_ticket.messages = []
    mock_ticket.assigned_operator_id = operator_id

    mock_summary = MagicMock(spec=TicketCopilotSummaryModel)
    mock_summary.summary = "Краткая сводка проблемы с ЭЦП"
    mock_summary.suggested_line_code = "L2"
    mock_summary.suggested_response = "Инструкция по настройке плагина"
    mock_summary.recommended_chunk_ids = ["chunk_portal_reglament"]
    mock_summary.similar_resolved_tickets = []
    mock_ticket.copilot_summary = mock_summary

    mock_client = MagicMock()
    mock_client.full_name = "Иванов Иван"
    mock_client.email = "ivanov@test.ru"
    mock_client.client_profile = None
    mock_ticket.chat = MagicMock()
    mock_ticket.chat.client = mock_client

    mock_repo = AsyncMock(spec=OperatorRepository)
    mock_repo.get_ticket_workspace_data.return_value = mock_ticket
    mock_repo.assign_ticket_to_operator.return_value = mock_ticket

    mock_redis = AsyncMock()

    service = OperatorService(
        session=AsyncMock(),
        redis=mock_redis,
        operator_repo=mock_repo,
        ticket_repo=AsyncMock(),
        support_line_repo=AsyncMock(),
    )

    workspace = await service.open_ticket(
        user_id=operator_id, ticket_id=ticket_id
    )

    assert workspace.copilot_summary is not None
    assert workspace.copilot_summary.summary == "Краткая сводка проблемы с ЭЦП"
    assert workspace.copilot_summary.suggested_line_code == "L2"
    assert (
        workspace.copilot_summary.suggested_response
        == "Инструкция по настройке плагина"
    )


@pytest.mark.asyncio
async def test_open_ticket_when_summary_not_ready_unit() -> None:
    """Сценарий А: open_ticket отдает copilot_summary=None, если Taskiq еще не завершил генерацию."""
    ticket_id = uuid6.uuid7()
    operator_id = uuid6.uuid7()

    mock_ticket = MagicMock(spec=TicketModel)
    mock_ticket.id = ticket_id
    mock_ticket.chat_id = uuid6.uuid7()
    mock_ticket.priority = "P2"
    mock_ticket.status = TicketStatus.IN_PROGRESS.value
    mock_ticket.line = MagicMock()
    mock_ticket.line.code = "L1"
    mock_ticket.transfer_comment = None
    mock_ticket.messages = []
    mock_ticket.assigned_operator_id = operator_id
    mock_ticket.copilot_summary = None  # Подсказка еще не готова

    mock_client = MagicMock()
    mock_client.full_name = "Петров Петр"
    mock_client.email = "petrov@test.ru"
    mock_client.client_profile = None
    mock_ticket.chat = MagicMock()
    mock_ticket.chat.client = mock_client

    mock_repo = AsyncMock(spec=OperatorRepository)
    mock_repo.get_ticket_workspace_data.return_value = mock_ticket
    mock_repo.assign_ticket_to_operator.return_value = mock_ticket

    mock_redis = AsyncMock()

    service = OperatorService(
        session=AsyncMock(),
        redis=mock_redis,
        operator_repo=mock_repo,
        ticket_repo=AsyncMock(),
        support_line_repo=AsyncMock(),
    )

    workspace = await service.open_ticket(
        user_id=operator_id, ticket_id=ticket_id
    )

    assert workspace.copilot_summary is None


# =========================================================================
# 6. Тесты фоновой задачи Taskiq generate_copilot_summary (юнит-уровень)
# =========================================================================


@pytest.mark.asyncio
async def test_generate_copilot_summary_task_flow_mocked() -> None:
    """Проверяет сценарий работы задачи generate_copilot_summary с mock-хранилищами."""
    ticket_id = uuid6.uuid7()
    operator_id = uuid6.uuid7()

    mock_ticket = MagicMock()
    mock_ticket.id = ticket_id
    mock_ticket.assigned_operator_id = operator_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.get.return_value = mock_ticket
    # select existing returns None (insert path)
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_session.scalars.return_value = scalars_mock

    session_maker_mock = MagicMock()
    session_maker_mock.return_value.__aenter__.return_value = mock_session

    mock_redis = AsyncMock()
    mock_redis.lrange.return_value = []

    with (
        patch("src.rag.tasks.aioredis.from_url", return_value=mock_redis),
        patch("src.rag.tasks.async_session_maker", session_maker_mock),
        patch("src.rag.tasks.RedisOperatorEvents") as mock_op_events_cls,
    ):
        mock_events_instance = AsyncMock()
        mock_op_events_cls.return_value = mock_events_instance

        res = await generate_copilot_summary({"ticket_id": str(ticket_id)})

        assert res["status"] == "success"
        assert res["ticket_id"] == str(ticket_id)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_events_instance.publish_copilot_ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_copilot_failure_isolation_task_mocked() -> None:
    """Проверяет изоляцию сбоя: при падении LLM задача сохраняет деградированную подсказку."""
    ticket_id = uuid6.uuid7()

    mock_ticket = MagicMock()
    mock_ticket.id = ticket_id
    mock_ticket.assigned_operator_id = None

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.get.return_value = mock_ticket
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_session.scalars.return_value = scalars_mock

    session_maker_mock = MagicMock()
    session_maker_mock.return_value.__aenter__.return_value = mock_session

    mock_redis = AsyncMock()
    mock_redis.lrange.return_value = []

    with (
        patch("src.rag.tasks.aioredis.from_url", return_value=mock_redis),
        patch("src.rag.tasks.async_session_maker", session_maker_mock),
        patch.object(
            CopilotService,
            "build_copilot_summary",
            side_effect=TimeoutError("LLM Down"),
        ),
    ):
        res = await generate_copilot_summary({"ticket_id": str(ticket_id)})

        assert res["status"] == "degraded"
        assert "Не удалось автоматически сформировать" in res["summary"]
        mock_session.add.assert_called_once()
        saved_summary = mock_session.add.call_args[0][0]
        assert isinstance(saved_summary, TicketCopilotSummaryModel)
        assert saved_summary.suggested_response is None


# =========================================================================
# 7. Интеграционные тесты с PostgreSQL (Testcontainers)
# =========================================================================


@pytest.mark.asyncio
async def test_ticket_copilot_summary_persistence(
    async_session: AsyncSession,
) -> None:
    """Проверяет сохранение, извлечение и каскадное удаление модели TicketCopilotSummaryModel."""
    # 1. Создаем пользователя, чат и тикет
    stmt = select(RoleModel).where(RoleModel.code == "client")
    role = (await async_session.scalars(stmt)).first()
    if not role:
        role = RoleModel(code="client", name="Клиент", description="Клиент")
        async_session.add(role)
        await async_session.flush()

    user = UserModel(
        email=f"copilot_user_{uuid.uuid4().hex[:8]}@test.ru",
        password_hash="hash",
        role_id=role.id,
    )
    async_session.add(user)
    await async_session.flush()

    chat = ChatModel(client_id=user.id)
    async_session.add(chat)
    await async_session.flush()

    ticket = TicketModel(chat_id=chat.id, status=TicketStatus.QUEUED.value)
    async_session.add(ticket)
    await async_session.flush()

    # 2. Создаем подсказку Copilot
    summary_record = TicketCopilotSummaryModel(
        ticket_id=ticket.id,
        summary="Краткая суть проблемы клиента",
        suggested_line_code="L2",
        suggested_response="Черновик решения",
        recommended_chunk_ids=["chunk_1", "chunk_2"],
        similar_resolved_tickets=[
            {
                "ticket_id": "018e0000-0000-7000-8000-000000000001",
                "support_line": "L2",
                "user_query": "Вопрос",
                "solution_text": "Ответ",
                "similarity_score": 0.95,
            }
        ],
    )
    async_session.add(summary_record)
    await async_session.commit()

    # 3. Извлекаем и проверяем отношение
    stmt_ticket = (
        select(TicketModel)
        .where(TicketModel.id == ticket.id)
        .options(selectinload(TicketModel.copilot_summary))
        .execution_options(populate_existing=True)
    )
    refreshed_ticket = (await async_session.scalars(stmt_ticket)).first()
    assert refreshed_ticket is not None
    assert refreshed_ticket.copilot_summary is not None
    assert (
        refreshed_ticket.copilot_summary.summary
        == "Краткая суть проблемы клиента"
    )
    assert refreshed_ticket.copilot_summary.suggested_line_code == "L2"
    assert len(refreshed_ticket.copilot_summary.recommended_chunk_ids) == 2
    assert len(refreshed_ticket.copilot_summary.similar_resolved_tickets) == 1

    # 4. Проверяем каскадное удаление: удаление тикета удаляет и подсказку
    await async_session.delete(refreshed_ticket)
    await async_session.commit()

    stmt = select(TicketCopilotSummaryModel).where(
        TicketCopilotSummaryModel.ticket_id == ticket.id
    )
    deleted_summary = (await async_session.scalars(stmt)).first()
    assert deleted_summary is None
