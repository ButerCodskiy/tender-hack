"""Брокер задач и планировщик Taskiq."""

import logging
from collections.abc import AsyncGenerator

import taskiq_fastapi
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.config import settings

logger = logging.getLogger(__name__)

ACTIVE_TASKIQ_QUEUES: list[str] = [
    "taskiq",
    "dispatch_queue",
    "copilot_queue",
    "analytics_queue",
    "ingestion_queue",
]


class MultiQueueRedisBroker(ListQueueBroker):
    """ListQueueBroker с поддержкой одновременного прослушивания всех очередей задач."""

    async def listen(self) -> AsyncGenerator[bytes, None]:
        redis_brpop_data_position = 1
        while True:
            try:
                async with Redis(
                    connection_pool=self.connection_pool
                ) as redis_conn:
                    brpop_result = await redis_conn.brpop(ACTIVE_TASKIQ_QUEUES)
                    if brpop_result is None:
                        continue
                    yield brpop_result[redis_brpop_data_position]
            except RedisConnectionError as exc:
                logger.warning("Redis connection error: %s", exc)
                continue


result_backend = RedisAsyncResultBackend(
    redis_url=settings.REDIS_URL,
)

broker = MultiQueueRedisBroker(
    url=settings.REDIS_URL,
    socket_timeout=None,
).with_result_backend(result_backend)

taskiq_fastapi.init(broker, "src.main:app")

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)
