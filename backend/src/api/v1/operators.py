from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import (
    CurrentOperatorDep,
    CurrentOperatorSseDep,
    OperatorServiceDep,
)
from src.chat.schemas import MessageResponseSchema
from src.operators.schemas import (
    OperatorProfileResponseSchema,
    OperatorSendMessageRequestSchema,
    OperatorShiftStatusUpdateSchema,
    OperatorSidebarTicketSchema,
    OperatorTicketWorkspaceSchema,
    ResolveTicketResponseSchema,
    TransferTicketRequestSchema,
    TransferTicketResponseSchema,
)

router = APIRouter(prefix="/operators", tags=["operators"])


@router.get(
    "/me/shift",
    summary="Получение параметров смены и занятых слотов оператора",
)
async def get_my_shift(
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> OperatorProfileResponseSchema:
    """Возвращает информацию о текущей рабочей смене и занятых слотах оператора."""
    return await service.get_profile(operator.id)


@router.patch(
    "/me/shift",
    summary="Обновление статуса рабочей смены оператора",
)
async def update_my_shift(
    payload: OperatorShiftStatusUpdateSchema,
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> OperatorProfileResponseSchema:
    """Переключает статус смены: active, break, offline."""
    return await service.update_shift(operator.id, payload.shift_status)


@router.get(
    "/events",
    response_class=StreamingResponse,
    summary="Постоянный входящий поток асинхронных событий оператора",
)
async def get_operator_events(
    request: Request,
    operator: CurrentOperatorSseDep,
    service: OperatorServiceDep,
) -> StreamingResponse:
    """Постоянный поток событий оператора по протоколу Server-Sent Events (SSE).

    Доставляет асинхронные события:
    - ticket_assigned (назначение нового обращения в сайдбар),
    - client_message (сообщение клиента по активному тикету),
    - copilot_ready (готовность подсказки Copilot).

    Контролирует онлайн-статус и отметку disconnected_at в профиле оператора.
    """
    event_generator = service.stream_operator_events(
        operator_id=operator.id,
        request=request,
    )
    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/tickets",
    summary="Получение списка закрепленных обращений для сайдбара",
)
async def get_my_tickets(
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> list[OperatorSidebarTicketSchema]:
    """Возвращает список тикетов в статусах assigned и in_progress, закрепленных за оператором."""
    return await service.get_sidebar_tickets(operator.id)


@router.post(
    "/tickets/{ticket_id}/open",
    summary="Открытие карточки обращения оператором и получение контекста",
)
async def open_ticket(
    ticket_id: UUID,
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> OperatorTicketWorkspaceSchema:
    """Открывает тикет, переводит в in_progress, уведомляет клиента и возвращает рабочий контекст."""
    return await service.open_ticket(operator.id, ticket_id)


@router.post(
    "/tickets/{ticket_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Отправка текстового ответа клиенту оператором",
)
async def send_message(
    ticket_id: UUID,
    payload: OperatorSendMessageRequestSchema,
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> MessageResponseSchema:
    """Фиксирует ответ оператора, выполняет модерацию и транслирует в шину событий."""
    return await service.send_message(operator.id, ticket_id, payload.text)


@router.post(
    "/tickets/{ticket_id}/transfer",
    summary="Перевод обращения на другую линию поддержки",
)
async def transfer_ticket(
    ticket_id: UUID,
    payload: TransferTicketRequestSchema,
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> TransferTicketResponseSchema:
    """Переводит тикет на другую линию, освобождая слот текущего специалиста."""
    return await service.transfer_ticket(
        operator.id,
        ticket_id,
        payload.target_line_code,
        payload.transfer_comment,
    )


@router.post(
    "/tickets/{ticket_id}/resolve",
    summary="Успешное завершение обращения специалистом",
)
async def resolve_ticket(
    ticket_id: UUID,
    operator: CurrentOperatorDep,
    service: OperatorServiceDep,
) -> ResolveTicketResponseSchema:
    """Завершает тикет, освобождает рабочий слот и запускает диспетчеризацию очереди."""
    return await service.resolve_ticket(operator.id, ticket_id)
