"""Клиент оперативного хранилища Redis, контекст диалогов и очереди линий."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from types import TracebackType
from uuid import UUID

import redis.asyncio as aioredis
import uuid6
from fastapi import Request
from pydantic import BaseModel

from src.core.config import settings


def _format_pubsub_to_sse(raw_data: str | bytes) -> str:
    """Преобразует JSON-сообщение из канала Pub/Sub в строку формата SSE с полем id."""
    text_data = (
        raw_data.decode("utf-8")
        if isinstance(raw_data, bytes)
        else str(raw_data)
    )
    try:
        parsed = json.loads(text_data)
        event_name = parsed.get("event", "message")
        payload = parsed.get("data", {})
        event_id = None
        if isinstance(payload, dict):
            event_id = payload.get("id") or payload.get("message_id")
        if not event_id and isinstance(parsed, dict):
            event_id = parsed.get("id")
        if not event_id:
            event_id = str(uuid6.uuid7())
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)
        return f"id: {event_id}\nevent: {event_name}\ndata: {payload_str}\n\n"
    except Exception:
        return f"data: {text_data}\n\n"


class RedisChatContext:
    """Адаптер скользящего окна оперативного контекста диалога в Redis."""

    def __init__(self, redis: aioredis.Redis) -> None:
        """Инициализирует адаптер контекста клиентом Redis."""
        self.redis = redis

    async def add_message(
        self,
        ticket_id: UUID | str,
        sender: str,
        text: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Добавляет реплику в контекст, обрезает окно до лимита и продлевает время жизни."""
        if timestamp is None:
            timestamp = datetime.now(settings.TIMEZONE)

        key = f"chat:context:{ticket_id}"
        payload = json.dumps(
            {
                "sender": sender,
                "text": text,
                "timestamp": timestamp.isoformat(),
            },
            ensure_ascii=False,
        )

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -settings.CHAT_CONTEXT_MAX_MESSAGES, -1)
            pipe.expire(key, settings.CHAT_CONTEXT_TTL_SECONDS)
            await pipe.execute()

    async def get_messages(self, ticket_id: UUID | str) -> list[dict]:
        """Извлекает сохраненный список реплик контекста обращения."""
        items = await self.redis.lrange(f"chat:context:{ticket_id}", 0, -1)
        return [json.loads(item) for item in items]

    async def clear_context(self, ticket_id: UUID | str) -> None:
        """Удаляет ключ оперативного контекста при завершении обращения."""
        await self.redis.delete(f"chat:context:{ticket_id}")

    async def get_ttl(self, ticket_id: UUID | str) -> int:
        """Возвращает оставшееся время жизни ключа контекста в секундах."""
        return await self.redis.ttl(f"chat:context:{ticket_id}")

    async def close(self) -> None:
        """Закрывает пул соединений с Redis."""
        await self.redis.aclose()


class RedisLineQueue:
    """Адаптер очереди обращений по линиям поддержки в Redis."""

    def __init__(self, redis: aioredis.Redis) -> None:
        """Инициализирует очередь клиентом Redis."""
        self.redis = redis

    async def enqueue_ticket(
        self,
        line_code: str,
        ticket_id: UUID | str,
        priority: str = "P2",
    ) -> int:
        """Помещает идентификатор тикета в очередь линии с учетом приоритета.

        Критические тикеты P0 добавляются в начало очереди через LPUSH для соблюдения SLA.
        Тикеты стандартных приоритетов P1 и P2 добавляются в конец очереди через RPUSH.
        """
        norm_priority = str(priority).upper()
        if norm_priority not in {"P0", "P1", "P2"}:
            raise ValueError(
                f"Недопустимый приоритет тикета: {priority!r}. "
                "Допустимые значения: 'P0', 'P1', 'P2'."
            )

        key = f"queue:line:{line_code}"
        val = str(ticket_id)
        if norm_priority == "P0":
            return await self.redis.lpush(key, val)
        return await self.redis.rpush(key, val)

    async def requeue_to_head(
        self, line_code: str, ticket_id: UUID | str
    ) -> int:
        """Возвращает идентификатор тикета в начало очереди линии (LPUSH)."""
        return await self.redis.lpush(
            f"queue:line:{line_code}", str(ticket_id)
        )

    requeue_ticket_front = requeue_to_head

    def get_dispatch_lock(
        self, line_code: str, ttl_seconds: int = 5
    ) -> "RedisDistributedLock":
        """Создает распределенную блокировку для линии поддержки."""
        return RedisDistributedLock(
            redis=self.redis,
            key=f"lock:dispatch:line:{line_code}",
            ttl_seconds=ttl_seconds,
        )

    def get_timeouts_lock(
        self, ttl_seconds: int = 25
    ) -> "RedisDistributedLock":
        """Создает распределенную блокировку для фоновой задачи контроля таймаутов."""
        return RedisDistributedLock(
            redis=self.redis,
            key="lock:check_system_timeouts",
            ttl_seconds=ttl_seconds,
        )

    def get_recovery_lock(
        self, ttl_seconds: int = 30
    ) -> "RedisDistributedLock":
        """Создает распределенную блокировку для аварийного восстановления очередей при старте."""
        return RedisDistributedLock(
            redis=self.redis,
            key="lock:queue_recovery",
            ttl_seconds=ttl_seconds,
        )

    async def rebuild_line_queue(
        self, line_code: str, ticket_ids: list[UUID | str]
    ) -> None:
        """Атомарно перезаливает упорядоченную очередь линии в Redis через pipeline."""
        key = f"queue:line:{line_code}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if ticket_ids:
                str_ids = [str(tid) for tid in ticket_ids]
                pipe.rpush(key, *str_ids)
            await pipe.execute()

    async def dequeue_ticket(self, line_code: str) -> str | None:
        """Извлекает первый идентификатор тикета из начала очереди линии (LPOP)."""
        return await self.redis.lpop(f"queue:line:{line_code}")

    async def get_queue_len(self, line_code: str) -> int:
        """Возвращает текущую длину очереди линии поддержки."""
        return await self.redis.llen(f"queue:line:{line_code}")

    async def peek_tickets(
        self, line_code: str, start: int = 0, stop: int = -1
    ) -> list[str]:
        """Возвращает список идентификаторов тикетов в очереди без их извлечения."""
        return await self.redis.lrange(f"queue:line:{line_code}", start, stop)

    async def clear_queue(self, line_code: str) -> None:
        """Очищает очередь линии поддержки."""
        await self.redis.delete(f"queue:line:{line_code}")

    async def close(self) -> None:
        """Закрывает клиент Redis."""
        await self.redis.aclose()


class RedisDistributedLock:
    """Асинхронный контекстный менеджер распределенной блокировки в Redis.

    Захватывает ключ с заданным временем жизни через SET NX EX.
    При выходе атомарно освобождает ключ с помощью Lua-скрипта,
    гарантируя удаление только собственной активной блокировки.
    """

    UNLOCK_LUA_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        key: str,
        ttl_seconds: int = 5,
        token: str | None = None,
    ) -> None:
        """Инициализирует параметры распределенной блокировки."""
        self.redis = redis
        self.key = key
        self.ttl_seconds = ttl_seconds
        self.token = token or str(uuid.uuid4())
        self.acquired: bool = False

    async def acquire(self) -> bool:
        """Пытается атомарно захватить распределенную блокировку в Redis."""
        result = await self.redis.set(
            self.key,
            self.token,
            nx=True,
            ex=self.ttl_seconds,
        )
        self.acquired = bool(result)
        return self.acquired

    async def release(self) -> bool:
        """Атомарно освобождает блокировку через Lua-скрипт с проверкой владельца."""
        if not self.acquired:
            return False
        result = await self.redis.eval(
            self.UNLOCK_LUA_SCRIPT,
            1,
            self.key,
            self.token,
        )
        self.acquired = False
        return bool(result)

    async def __aenter__(self) -> bool:
        """Вход в асинхронный контекст: захват блокировки."""
        return await self.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Выход из асинхронного контекста: гарантированное снятие блокировки."""
        await self.release()


class RedisOperatorEvents:
    """Адаптер шины событий операторов в Redis Pub/Sub."""

    def __init__(self, redis: aioredis.Redis) -> None:
        """Инициализирует адаптер клиентом Redis."""
        self.redis = redis

    async def publish_ticket_assigned(
        self,
        operator_id: UUID | str,
        data: dict | BaseModel,
    ) -> int:
        """Публикует событие назначения тикета в канал оператора.

        Канал: channel:operator:{operator_id}
        Событие: ticket_assigned
        """
        payload_data = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else data
        )
        message = json.dumps(
            {
                "event": "ticket_assigned",
                "data": payload_data,
            },
            ensure_ascii=False,
            default=str,
        )
        channel = f"channel:operator:{operator_id}"
        return await self.redis.publish(channel, message)

    async def publish_client_message(
        self,
        operator_id: UUID | str,
        data: dict | BaseModel,
    ) -> int:
        """Публикует входящее сообщение клиента в канал оператора.

        Канал: channel:operator:{operator_id}
        Событие: client_message
        """
        payload_data = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else data
        )
        message = json.dumps(
            {
                "event": "client_message",
                "data": payload_data,
            },
            ensure_ascii=False,
            default=str,
        )
        channel = f"channel:operator:{operator_id}"
        return await self.redis.publish(channel, message)

    async def publish_copilot_ready(
        self,
        operator_id: UUID | str,
        data: dict | BaseModel,
    ) -> int:
        """Публикует событие готовности подсказки Copilot в канал оператора.

        Канал: channel:operator:{operator_id}
        Событие: copilot_ready
        """
        payload_data = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else data
        )
        message = json.dumps(
            {
                "event": "copilot_ready",
                "data": payload_data,
            },
            ensure_ascii=False,
            default=str,
        )
        channel = f"channel:operator:{operator_id}"
        return await self.redis.publish(channel, message)

    async def incr_operator_connections(self, operator_id: UUID | str) -> int:
        """Увеличивает счетчик открытых SSE-соединений оператора."""
        key = f"operator:connections:{operator_id}"
        return await self.redis.incr(key)

    async def decr_operator_connections(self, operator_id: UUID | str) -> int:
        """Уменьшает счетчик открытых SSE-соединений оператора."""
        key = f"operator:connections:{operator_id}"
        val = await self.redis.decr(key)
        if val < 0:
            await self.redis.set(key, 0)
            return 0
        return val

    async def subscribe_operator_events(
        self,
        operator_id: UUID | str,
        request: Request | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """Асинхронный генератор событий оператора из Redis Pub/Sub."""
        channel = f"channel:operator:{operator_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        last_ping = asyncio.get_running_loop().time()
        try:
            while True:
                if request is not None and await request.is_disconnected():
                    break
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if msg is not None and msg.get("type") == "message":
                    data = msg.get("data")
                    if data is not None:
                        yield _format_pubsub_to_sse(data)
                        last_ping = asyncio.get_running_loop().time()
                else:
                    now = asyncio.get_running_loop().time()
                    if now - last_ping >= heartbeat_interval:
                        yield ": ping\n\n"
                        last_ping = now
        finally:

            async def _cleanup() -> None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:
                    pass
                try:
                    await pubsub.close()
                except Exception:
                    pass

            await asyncio.shield(_cleanup())

    async def close(self) -> None:
        """Закрывает клиент Redis."""
        await self.redis.aclose()


class RedisTicketEvents:
    """Адаптер событий диалога в Redis Pub/Sub по каналу channel:ticket:{ticket_id}."""

    def __init__(self, redis: aioredis.Redis) -> None:
        """Инициализирует адаптер клиентом Redis."""
        self.redis = redis

    async def publish_operator_joined(
        self, ticket_id: UUID | str, operator_name: str
    ) -> int:
        """Публикует событие подключения оператора к диалогу."""
        message = json.dumps(
            {
                "event": "operator_joined",
                "data": {
                    "ticket_id": str(ticket_id),
                    "operator_name": operator_name,
                },
            },
            ensure_ascii=False,
            default=str,
        )
        return await self.redis.publish(f"channel:ticket:{ticket_id}", message)

    async def publish_new_message(
        self, ticket_id: UUID | str, message_data: dict | BaseModel
    ) -> int:
        """Публикует событие новой реплики в диалоге."""
        payload_data = (
            message_data.model_dump(mode="json")
            if isinstance(message_data, BaseModel)
            else message_data
        )
        message = json.dumps(
            {
                "event": "new_message",
                "data": payload_data,
            },
            ensure_ascii=False,
            default=str,
        )
        return await self.redis.publish(f"channel:ticket:{ticket_id}", message)

    async def publish_ticket_transferred(
        self,
        ticket_id: UUID | str,
        new_line_code: str,
        reason: str | None = None,
    ) -> int:
        """Публикует событие перевода обращения на другую линию."""
        message = json.dumps(
            {
                "event": "ticket_transferred",
                "data": {
                    "ticket_id": str(ticket_id),
                    "new_line_code": new_line_code,
                    "reason": reason,
                },
            },
            ensure_ascii=False,
            default=str,
        )
        return await self.redis.publish(f"channel:ticket:{ticket_id}", message)

    async def publish_ticket_resolved(
        self,
        ticket_id: UUID | str,
        operator_id: UUID | str | None = None,
        closed_at: datetime | None = None,
    ) -> int:
        """Публикует событие успешного завершения обращения."""
        if closed_at is None:
            closed_at = datetime.now(settings.TIMEZONE)
        message = json.dumps(
            {
                "event": "ticket_resolved",
                "data": {
                    "ticket_id": str(ticket_id),
                    "operator_id": str(operator_id) if operator_id else None,
                    "closed_at": closed_at.isoformat(),
                },
            },
            ensure_ascii=False,
            default=str,
        )
        return await self.redis.publish(f"channel:ticket:{ticket_id}", message)

    async def publish_ticket_closed_inactivity(
        self,
        ticket_id: UUID | str,
        data: dict | BaseModel | None = None,
    ) -> int:
        """Публикует событие закрытия тикета по неактивности."""
        payload_data = (
            data.model_dump(mode="json")
            if isinstance(data, BaseModel)
            else (data or {"ticket_id": str(ticket_id)})
        )
        message = json.dumps(
            {
                "event": "ticket_closed_inactivity",
                "data": payload_data,
            },
            ensure_ascii=False,
            default=str,
        )
        return await self.redis.publish(f"channel:ticket:{ticket_id}", message)

    async def subscribe_ticket_events(
        self,
        ticket_id: UUID | str,
        request: Request | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """Асинхронный генератор событий тикета из Redis Pub/Sub."""
        channel = f"channel:ticket:{ticket_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        last_ping = asyncio.get_running_loop().time()
        try:
            while True:
                if request is not None and await request.is_disconnected():
                    break
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if msg is not None and msg.get("type") == "message":
                    data = msg.get("data")
                    if data is not None:
                        yield _format_pubsub_to_sse(data)
                        last_ping = asyncio.get_running_loop().time()
                else:
                    now = asyncio.get_running_loop().time()
                    if now - last_ping >= heartbeat_interval:
                        yield ": ping\n\n"
                        last_ping = now
        finally:

            async def _cleanup() -> None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:
                    pass
                try:
                    await pubsub.close()
                except Exception:
                    pass

            await asyncio.shield(_cleanup())

    async def close(self) -> None:
        """Закрывает клиент Redis."""
        await self.redis.aclose()


# Псевдонимы для обратной совместимости
RedisChatContextManager = RedisChatContext
RedisLineQueueManager = RedisLineQueue
RedisOperatorEventsManager = RedisOperatorEvents
RedisTicketEventsManager = RedisTicketEvents
