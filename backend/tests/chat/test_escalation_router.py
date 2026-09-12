"""Тесты сервиса маршрутизации эскалации EscalationRouter и выбора линий L1/L2."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import uuid6

from src.chat.models import (
    ChatModel,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.router import (
    EscalationRouteOutput,
    EscalationRouter,
    build_escalation_prompt,
)
from src.chat.schemas import EscalateRequestSchema
from src.chat.service import ChatService
from src.core.config import settings
from src.operators.models import SupportLineModel


@pytest.mark.asyncio
async def test_escalation_router_routes_to_l2() -> None:
    """Проверяет корректный выбор технической линии L2 при сбоях ЭЦП."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "line": "L2",
        "reason": "Обнаружена ошибка плагина КриптоПро и сбой подписания оферты",
    }

    router = EscalationRouter(llm_client=mock_llm, timeout=15.0)
    history = [
        {
            "role": "user",
            "text": "Не могу подписать контракт, ошибка 0x80090016",
        },
        {"role": "assistant", "text": "Попробуйте обновить плагин"},
    ]

    result = await router.route(
        conversation_history=history,
        client_reason="Срочно, не работает ЭЦП",
    )

    assert result.line == "L2"
    assert "КриптоПро" in result.reason
    mock_llm.generate_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_escalation_router_routes_to_l1() -> None:
    """Проверяет корректный выбор консультационной линии L1 по регламентам."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "line": "L1",
        "reason": "Вопрос касается регламента проведения котировочных сессий",
    }

    router = EscalationRouter(llm_client=mock_llm, timeout=15.0)
    history = [
        {
            "role": "user",
            "text": "Подскажите сроки подачи ценовых предложений",
        },
    ]

    result = await router.route(
        conversation_history=history,
        client_reason="Нужна консультация человека",
    )

    assert result.line == "L1"
    assert "регламент" in result.reason.lower()


@pytest.mark.asyncio
async def test_escalation_router_fallback_on_timeout() -> None:
    """Проверяет безопасный фолбэк на L1 при превышении таймаута модели."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.side_effect = TimeoutError("Ollama JSON timeout")

    router = EscalationRouter(llm_client=mock_llm, timeout=15.0)
    history = [{"role": "user", "text": "Любой текст"}]

    result = await router.route(conversation_history=history)

    assert result.line == "L1"
    assert "фолбэк" in result.reason.lower()


@pytest.mark.asyncio
async def test_escalation_router_normalizes_line() -> None:
    """Проверяет нормализацию строковых вариантов ответа модели."""
    assert EscalationRouter._normalize_line("L2") == "L2"
    assert EscalationRouter._normalize_line("l2") == "L2"
    assert EscalationRouter._normalize_line("Линия 2") == "L2"
    assert EscalationRouter._normalize_line("Техническая") == "L2"
    assert EscalationRouter._normalize_line("L1") == "L1"
    assert EscalationRouter._normalize_line("l1") == "L1"
    assert EscalationRouter._normalize_line("непонятно") == "L1"
    assert EscalationRouter._normalize_line(None) == "L1"


def test_build_escalation_prompt() -> None:
    """Проверяет сборку текстового контекста для промпта."""
    history = [
        {"sender": "client", "text": "Сообщение 1"},
        {"sender": "bot", "text": "Ответ бота"},
    ]
    prompt = build_escalation_prompt(history, client_reason="Помогите")
    assert "[client]: Сообщение 1" in prompt
    assert "[bot]: Ответ бота" in prompt
    assert "Помогите" in prompt


@pytest.mark.asyncio
async def test_chat_service_escalate_with_router() -> None:
    """Проверяет сквозную эскалацию тикета в ChatService с выбором линии через EscalationRouter."""
    user_id = uuid6.uuid7()
    chat_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    chat = ChatModel(id=chat_id, client_id=user_id)
    ticket = TicketModel(
        id=ticket_id,
        chat_id=chat_id,
        priority=TicketPriority.P1,
        status=TicketStatus.BOT_PROCESSING.value,
        created_at=datetime.now(settings.TIMEZONE),
    )

    mock_chat_repo = AsyncMock()
    mock_chat_repo.get_by_client_id.return_value = chat
    mock_chat_repo.get_recent_messages.return_value = []

    mock_ticket_repo = AsyncMock()
    mock_ticket_repo.get_active_by_chat_id.return_value = ticket

    mock_session = AsyncMock()
    mock_line_queue = AsyncMock()

    mock_router = AsyncMock(spec=EscalationRouter)
    mock_router.route.return_value = EscalationRouteOutput(
        line="L2",
        reason="Сбой плагина ЭЦП",
    )

    from unittest.mock import MagicMock

    l2_line = SupportLineModel(id=2, code="L2", name="Вторая линия")
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = l2_line
    mock_session.scalars.return_value = mock_scalars

    service = ChatService(
        repo=mock_chat_repo,
        session=mock_session,
        rag_service=AsyncMock(),
        ticket_repo=mock_ticket_repo,
        line_queue=mock_line_queue,
        escalation_router=mock_router,
    )

    # Мокаем фоновые задачи во избежание внешних вызовов Taskiq
    service._safe_dispatch_task = AsyncMock()
    service._safe_copilot_task = AsyncMock()

    from src.auth.models import UserModel

    user = UserModel(
        id=user_id,
        email="test_client@zakupki.mos.ru",
        password_hash="fake",
        full_name="Тестовый Заказчик",
        is_active=True,
    )

    payload = EscalateRequestSchema(reason="Не могу подписать контракт")
    result = await service.escalate_ticket(user=user, payload=payload)

    assert result.id == ticket_id
    assert result.status == TicketStatus.QUEUED.value
    assert result.line_code == "L2"
    assert ticket.line_id == 2
    assert ticket.escalation_reason == "Не могу подписать контракт"

    # Проверка, что тикет отправлен в очередь линии L2
    mock_line_queue.enqueue_ticket.assert_awaited_once_with(
        line_code="L2",
        ticket_id=ticket_id,
        priority=TicketPriority.P1,
    )
    service._safe_dispatch_task.assert_awaited_once_with(
        "L2", "ticket_escalated"
    )
    service._safe_copilot_task.assert_awaited_once_with(ticket_id)
