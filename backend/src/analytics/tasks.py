"""Фоновые задачи Taskiq домена analytics (аудит диалогов и расчет метрик)."""

import logging
from datetime import date
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from src.analytics.schemas import (
    AuditTicketPayloadSchema,
    DailyMetricsPayloadSchema,
)
from src.analytics.service import AnalyticsService
from src.core.broker import broker
from src.core.config import settings
from src.core.redis_client import RedisDistributedLock
from src.db.database import async_session_maker

logger = logging.getLogger(__name__)


@broker.task(
    task_name="audit_ticket_quality",
    queue_name="analytics_queue",
    max_retries=3,
    retry_delay=5,
)
async def audit_ticket_quality(
    payload: AuditTicketPayloadSchema | dict[str, Any],
) -> dict[str, Any]:
    """Фоновая задача Taskiq для автоматического контроля качества закрытого диалога.

    1. Валидирует полезную нагрузку (ticket_id, trigger_reason).
    2. Создает изолированное асинхронное подключение к PostgreSQL и клиенту Redis.
    3. Вызывает доменный сервис AnalyticsService.audit_ticket_quality.
    4. Обеспечивает Dead-Letter обработку при фатальных сбоях.
    """
    if isinstance(payload, dict):
        validated_payload = AuditTicketPayloadSchema.model_validate(payload)
    else:
        validated_payload = payload

    ticket_id: UUID = validated_payload.ticket_id
    trigger_reason: str = validated_payload.trigger_reason
    logger.info(
        "Запуск фонового аудита качества диалога для тикета %s (причина: %s)",
        ticket_id,
        trigger_reason,
    )

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async with async_session_maker() as session:
            service = AnalyticsService(session=session, redis=redis)
            result = await service.audit_ticket_quality(
                ticket_id=ticket_id,
                trigger_reason=trigger_reason,
            )
            return result
    finally:
        await redis.aclose()


@broker.task(
    task_name="calculate_daily_metrics",
    queue_name="analytics_queue",
    schedule=[{"cron": "5 0 * * *"}],
    max_retries=2,
    retry_delay=10,
)
async def calculate_daily_metrics(
    payload: DailyMetricsPayloadSchema | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Фоновая периодическая задача Taskiq для суточной агрегации показателей операторов.

    Запускается ежедневно в 00:05 по московскому времени (cron: 5 0 * * *).
    Защищена распределенной блокировкой Redis lock:calculate_daily_metrics на 300 секунд.
    Поддерживает ручной запуск с передачей конкретной даты или operator_id в payload.
    """
    target_date: date | None = None
    target_operator_id: UUID | None = None

    if payload is not None:
        if isinstance(payload, dict):
            validated_payload = DailyMetricsPayloadSchema.model_validate(
                payload
            )
        else:
            validated_payload = payload

        if validated_payload.metric_date is not None:
            if isinstance(validated_payload.metric_date, str):
                target_date = date.fromisoformat(validated_payload.metric_date)
            else:
                target_date = validated_payload.metric_date

        if validated_payload.operator_id is not None:
            if isinstance(validated_payload.operator_id, str):
                target_operator_id = UUID(validated_payload.operator_id)
            else:
                target_operator_id = validated_payload.operator_id

    logger.info(
        "Запуск задачи calculate_daily_metrics (target_date=%s, operator_id=%s)",
        target_date,
        target_operator_id,
    )

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        lock = RedisDistributedLock(
            redis=redis,
            key="lock:calculate_daily_metrics",
            ttl_seconds=300,
        )
        async with lock as acquired:
            if not acquired:
                logger.info(
                    "calculate_daily_metrics: распределенный лок занят другим воркером, пропуск"
                )
                return {"status": "skipped", "reason": "lock_busy"}

            async with async_session_maker() as session:
                service = AnalyticsService(session=session, redis=redis)
                result = await service.calculate_daily_metrics(
                    target_date=target_date,
                    operator_id=target_operator_id,
                )
                return result
    finally:
        await redis.aclose()
