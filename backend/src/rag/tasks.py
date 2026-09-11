"""Фоновые задачи Taskiq домена rag (подготовка copilot summary)."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select

from src.chat.models import MessageModel, TicketModel
from src.core.broker import broker
from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.core.redis_client import RedisChatContext, RedisOperatorEvents
from src.db.database import async_session_maker
from src.operators.models import TicketCopilotSummaryModel
from src.operators.schemas import CopilotSummaryResponseSchema
from src.rag.copilot import CopilotService
from src.rag.schemas import CopilotPayloadSchema

logger = logging.getLogger(__name__)


@broker.task(task_name="generate_copilot_summary", queue_name="copilot_queue")
async def generate_copilot_summary(
    payload: CopilotPayloadSchema | dict[str, Any],
) -> dict[str, Any]:
    """Фоновая задача Taskiq для подготовки аналитической подсказки оператору.

    1. Считывает историю переписки тикета из Redis (с фолбэком в PostgreSQL).
    2. Вызывает сервис CopilotService для суммаризации и поиска похожих закрытых кейсов.
    3. Выполняет идемпотентное сохранение (UPSERT) в таблицу ticket_copilot_summaries.
    4. При наличии закрепленного оператора отправляет SSE-событие copilot_ready через Redis Pub/Sub.
    5. Обеспечивает изоляцию сбоев: при ошибках LLM фиксирует деградированную подсказку.
    """
    if isinstance(payload, dict):
        validated_payload = CopilotPayloadSchema.model_validate(payload)
    else:
        validated_payload = payload

    ticket_id: UUID = validated_payload.ticket_id
    logger.info(
        "Запуск фоновой задачи подготовки подсказки Copilot для тикета %s",
        ticket_id,
    )

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    summary_status = "success"

    try:
        # 1. Загрузка реплик обращения из оперативного контекста Redis
        redis_context = RedisChatContext(redis)
        messages = await redis_context.get_messages(ticket_id)

        # 2. Подключение к БД PostgreSQL
        async with async_session_maker() as session:
            # Если в Redis контекст пуст, считываем историю из таблицы messages
            if not messages:
                stmt_msgs = (
                    select(MessageModel)
                    .where(MessageModel.ticket_id == ticket_id)
                    .order_by(MessageModel.created_at.asc())
                )
                db_msgs = (await session.scalars(stmt_msgs)).all()
                messages = [
                    {"sender": m.sender_type, "text": m.text} for m in db_msgs
                ]

            ticket = await session.get(TicketModel, ticket_id)
            if ticket is None:
                logger.warning(
                    "Обращение %s не найдено в БД, задача прервана", ticket_id
                )
                return {
                    "ticket_id": str(ticket_id),
                    "status": "ticket_not_found",
                }

            assigned_operator_id = ticket.assigned_operator_id

            # 3. Вызов сервиса генерации подсказки Copilot
            copilot_service = CopilotService(qdrant_client=get_qdrant_client())
            try:
                summary_dto = await copilot_service.build_copilot_summary(
                    ticket_id=ticket_id,
                    messages=messages,
                )
            except Exception as exc:
                logger.error(
                    "Сбой генерации подсказки Copilot для тикета %s (активирован fallback): %s",
                    ticket_id,
                    exc,
                )
                summary_status = "degraded"
                summary_dto = CopilotSummaryResponseSchema(
                    summary="Не удалось автоматически сформировать сводку обращения (таймаут генератора).",
                    suggested_line_code=None,
                    suggested_response=None,
                    recommended_chunk_ids=[],
                    similar_resolved_tickets=[],
                )

            # 4. Идемпотентный UPSERT в таблицу ticket_copilot_summaries
            stmt_existing = select(TicketCopilotSummaryModel).where(
                TicketCopilotSummaryModel.ticket_id == ticket_id
            )
            existing_summary = (await session.scalars(stmt_existing)).first()
            now = datetime.now(settings.TIMEZONE)

            serialized_tickets = [
                t.model_dump(mode="json")
                for t in summary_dto.similar_resolved_tickets
            ]

            if existing_summary is not None:
                existing_summary.summary = summary_dto.summary
                existing_summary.suggested_line_code = (
                    summary_dto.suggested_line_code
                )
                existing_summary.suggested_response = (
                    summary_dto.suggested_response
                )
                existing_summary.recommended_chunk_ids = (
                    summary_dto.recommended_chunk_ids
                )
                existing_summary.similar_resolved_tickets = serialized_tickets
                existing_summary.created_at = now
            else:
                new_summary = TicketCopilotSummaryModel(
                    ticket_id=ticket_id,
                    summary=summary_dto.summary,
                    suggested_line_code=summary_dto.suggested_line_code,
                    suggested_response=summary_dto.suggested_response,
                    recommended_chunk_ids=summary_dto.recommended_chunk_ids,
                    similar_resolved_tickets=serialized_tickets,
                    created_at=now,
                )
                session.add(new_summary)

            await session.commit()

        # 5. Оповещение закрепленного оператора через Redis Pub/Sub
        if assigned_operator_id is not None:
            operator_events = RedisOperatorEvents(redis)
            await operator_events.publish_copilot_ready(
                operator_id=assigned_operator_id,
                data=summary_dto,
            )
            logger.info(
                "Событие copilot_ready отправлено в канал оператора %s для тикета %s",
                assigned_operator_id,
                ticket_id,
            )

    finally:
        await redis.aclose()

    logger.info(
        "Завершена подготовка подсказки Copilot для тикета %s (статус: %s)",
        ticket_id,
        summary_status,
    )

    return {
        "ticket_id": str(ticket_id),
        "status": summary_status,
        "summary": summary_dto.summary,
        "suggested_line_code": summary_dto.suggested_line_code,
        "recommended_chunk_ids_count": len(summary_dto.recommended_chunk_ids),
        "similar_resolved_tickets_count": len(
            summary_dto.similar_resolved_tickets
        ),
    }
