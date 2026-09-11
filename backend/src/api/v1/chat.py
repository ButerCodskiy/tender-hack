from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from src.analytics.schemas import (
    FeedbackCreateRequestSchema,
    FeedbackResponseSchema,
)
from src.api.dependencies import (
    AnalyticsServiceDep,
    ChatServiceDep,
    CurrentClientDep,
    CurrentClientSseDep,
)
from src.chat.schemas import (
    ActiveTicketSummarySchema,
    CancelTicketResponseSchema,
    ChatStateResponseSchema,
    ClientResolveTicketResponseSchema,
    ClientSendMessageRequestSchema,
    EscalateRequestSchema,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получение текущего состояния переписки и истории клиента",
)
async def get_chat_state(
    current_user: CurrentClientDep,
    service: ChatServiceDep,
) -> ChatStateResponseSchema:
    """Возвращает сводку активного обращения, ленту сообщений и разрешенные действия."""
    return await service.get_chat_state(current_user)


@router.get(
    "/events",
    response_class=StreamingResponse,
    summary="Постоянный входящий поток асинхронных событий клиента",
)
async def get_chat_events(
    request: Request,
    current_user: CurrentClientSseDep,
    service: ChatServiceDep,
    ticket_id: Annotated[
        UUID | None,
        Query(description="Идентификатор конкретного обращения (опционально)"),
    ] = None,
    last_event_id: Annotated[
        str | None,
        Query(
            description="Идентификатор последнего полученного события (для переподключения)",
        ),
    ] = None,
) -> StreamingResponse:
    """Постоянный поток событий клиента по протоколу Server-Sent Events (SSE).

    Доставляет асинхронные события диалога:
    - operator_joined (подключение оператора к тикету),
    - new_message (входящая реплика от оператора),
    - ticket_resolved (успешное завершение обращения),
    - ticket_closed_inactivity (закрытие тикета по неактивности).
    Поддерживает возобновление передачи пропущенных сообщений по заголовку Last-Event-ID.
    """
    effective_last_event_id = (
        request.headers.get("last-event-id") or last_event_id
    )
    event_generator = service.stream_chat_events(
        user=current_user,
        ticket_id=ticket_id,
        request=request,
        last_event_id=effective_last_event_id,
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


@router.post(
    "/messages",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    summary="Отправка сообщения клиентом в чат поддержки",
)
async def send_message(
    payload: ClientSendMessageRequestSchema,
    current_user: CurrentClientDep,
    service: ChatServiceDep,
    request: Request,
) -> StreamingResponse:
    """Принимает вопрос клиента, оркестрирует конвейер обработки и отдает поток SSE."""
    accept_header = request.headers.get("accept")
    return StreamingResponse(
        service.process_client_message(
            payload=payload,
            user=current_user,
            accept_header=accept_header,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/escalate",
    status_code=status.HTTP_200_OK,
    summary="Ручной вызов оператора клиентом (эскалация)",
)
async def escalate_ticket(
    current_user: CurrentClientDep,
    service: ChatServiceDep,
    payload: EscalateRequestSchema | None = None,
) -> ActiveTicketSummarySchema:
    """Переводит текущее обращение в queued и запускает распределение по операторам."""
    return await service.escalate_ticket(user=current_user, payload=payload)


@router.post(
    "/tickets/{ticket_id}/resolve",
    status_code=status.HTTP_200_OK,
    summary="Подтверждение решения вопроса клиентом",
)
async def resolve_ticket(
    ticket_id: UUID,
    current_user: CurrentClientDep,
    service: ChatServiceDep,
) -> ClientResolveTicketResponseSchema:
    """Переводит обращение в статус resolved и фиксирует время закрытия."""
    return await service.resolve_ticket_by_client(
        user=current_user, ticket_id=ticket_id
    )


@router.post(
    "/tickets/{ticket_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Отмена обращения клиентом",
)
async def cancel_ticket(
    ticket_id: UUID,
    current_user: CurrentClientDep,
    service: ChatServiceDep,
) -> CancelTicketResponseSchema:
    """Отменяет обращение клиентом до начала диалога с оператором."""
    return await service.cancel_ticket_by_client(
        user=current_user, ticket_id=ticket_id
    )


@router.post(
    "/tickets/{ticket_id}/feedback",
    status_code=status.HTTP_201_CREATED,
    summary="Фиксация оценки качества обслуживания и отзыва клиента",
)
async def create_ticket_feedback(
    ticket_id: UUID,
    payload: FeedbackCreateRequestSchema,
    current_user: CurrentClientDep,
    analytics_service: AnalyticsServiceDep,
) -> FeedbackResponseSchema:
    """Фиксирует оценку диалога клиентом и инициирует фоновый аудит качества."""
    return await analytics_service.save_feedback(
        user_id=current_user.id,
        ticket_id=ticket_id,
        score=payload.score,
        comment=payload.comment,
    )
