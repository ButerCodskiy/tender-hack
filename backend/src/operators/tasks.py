"""Фоновые задачи Taskiq для домена operators."""

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis

from src.core.broker import broker
from src.core.config import settings
from src.core.redis_client import RedisDistributedLock
from src.db.database import async_session_maker
from src.operators.schemas import DispatchPayloadSchema
from src.operators.service import OperatorService

logger = logging.getLogger(__name__)


@broker.task(task_name="dispatch_line_queue", queue_name="dispatch_queue")
async def dispatch_line_queue(
    payload: DispatchPayloadSchema | dict[str, Any],
) -> dict[str, Any]:
    """Фоновая задача Taskiq для распределения обращений линии поддержки."""
    if isinstance(payload, dict):
        validated_payload = DispatchPayloadSchema.model_validate(payload)
    else:
        validated_payload = payload

    logger.info(
        "Запуск фоновой задачи распределения линии %s (причина: %s)",
        validated_payload.line_code,
        validated_payload.trigger_reason,
    )

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async with async_session_maker() as session:
            service = OperatorService(session=session, redis=redis)
            result = await service.dispatch_line(
                line_code=validated_payload.line_code,
                trigger_reason=validated_payload.trigger_reason,
            )
    finally:
        await redis.aclose()

    logger.info(
        "Завершена фоновая задача распределения линии %s: "
        "назначено %d тикетов, причина остановки: %s",
        result.line_code,
        result.assigned_count,
        result.stop_reason,
    )

    return {
        "line_code": result.line_code,
        "assigned_count": result.assigned_count,
        "assigned_ticket_ids": [
            str(tid) for tid in result.assigned_ticket_ids
        ],
        "stop_reason": result.stop_reason,
    }


@broker.task(
    task_name="check_system_timeouts",
    schedule=[{"interval": 30}],
)
async def check_system_timeouts() -> dict[str, Any]:
    """Фоновая периодическая задача контроля таймаутов, неактивности и связи операторов.

    Запускается каждые 30 секунд планировщиком Taskiq Scheduler.
    Защищена распределенной блокировкой Redis lock:check_system_timeouts на 25 секунд.
    Ограничена локальным таймаутом выполнения 20 секунд во избежание наложения воркеров.
    """
    logger.info(
        "Запуск периодической задачи проверки таймаутов check_system_timeouts"
    )
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        lock = RedisDistributedLock(
            redis=redis,
            key="lock:check_system_timeouts",
            ttl_seconds=25,
        )
        async with lock as acquired:
            if not acquired:
                logger.info(
                    "check_system_timeouts: распределенный лок занят другим воркером, пропуск выполнения"
                )
                return {"status": "skipped", "reason": "lock_busy"}

            try:
                async with asyncio.timeout(20.0):
                    async with async_session_maker() as session:
                        service = OperatorService(session=session, redis=redis)
                        result = await service.check_timeouts()
            except TimeoutError:
                logger.error(
                    "check_system_timeouts: превышен локальный таймаут 20 секунд, операция прервана"
                )
                return {
                    "status": "timeout",
                    "reason": "execution_timeout_exceeded",
                }

            logger.info(
                "Завершена проверка таймаутов: закрыто бот-тикетов=%d, "
                "предупреждений=%d, закрыто оператор-тикетов=%d, "
                "операторов offline=%d, тикетов возвращено=%d, линии=%s",
                result.bot_tickets_closed,
                result.operator_warnings_sent,
                result.operator_tickets_closed,
                result.operators_marked_offline,
                result.tickets_requeued,
                result.affected_line_codes,
            )
            return {
                "status": "success",
                "result": result.model_dump(),
            }
    finally:
        await redis.aclose()
