import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat.models import (
    TERMINAL_TICKET_STATUSES,
    MessageSenderType,
    TicketStatus,
)
from src.chat.moderation import (
    ProfanityModerator,
    ProfanityValidationError,
    get_moderator,
)
from src.chat.repository import TicketRepository
from src.chat.schemas import MessageResponseSchema
from src.core.config import settings
from src.core.redis_client import (
    RedisChatContext,
    RedisLineQueue,
    RedisOperatorEvents,
    RedisTicketEvents,
)
from src.db.database import async_session_maker
from src.operators.balancer import TicketBalancer
from src.operators.models import OperatorShiftStatus
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.schemas import (
    CheckTimeoutsResult,
    ClientInfoSchema,
    CopilotSummaryResponseSchema,
    DispatchPayloadSchema,
    DispatchResult,
    DispatchTriggerReason,
    OperatorProfileResponseSchema,
    OperatorSidebarTicketSchema,
    OperatorTicketWorkspaceSchema,
    ResolveTicketResponseSchema,
    TransferTicketResponseSchema,
)

logger = logging.getLogger(__name__)


class OperatorService:
    """Сервис управления операторами и оркестрации распределения обращений."""

    def __init__(
        self,
        session: AsyncSession,
        redis: aioredis.Redis,
        operator_repo: OperatorRepository | None = None,
        support_line_repo: SupportLineRepository | None = None,
        ticket_repo: TicketRepository | None = None,
        line_queue: RedisLineQueue | None = None,
        redis_events: RedisOperatorEvents | None = None,
        ticket_events: RedisTicketEvents | None = None,
        chat_context: RedisChatContext | None = None,
        moderator: ProfanityModerator | None = None,
        balancer: TicketBalancer | None = None,
    ) -> None:
        """Инициализирует сервис сессией БД, клиентом Redis, репозиториями и балансировщиком."""
        self.session = session
        self.redis = redis
        self.operator_repo = operator_repo or OperatorRepository(session)
        self.support_line_repo = support_line_repo or SupportLineRepository(
            session
        )
        self.ticket_repo = ticket_repo or TicketRepository(session)
        self.line_queue = line_queue or RedisLineQueue(redis)
        self.redis_events = redis_events or RedisOperatorEvents(redis)
        self.ticket_events = ticket_events or RedisTicketEvents(redis)
        self.chat_context = chat_context or RedisChatContext(redis)
        self.moderator = moderator or get_moderator()
        self.balancer = balancer or TicketBalancer(
            session=session,
            redis_events=self.redis_events,
            ticket_repo=self.ticket_repo,
            operator_repo=self.operator_repo,
        )

    async def dispatch_line(
        self,
        line_code: str,
        trigger_reason: DispatchTriggerReason | str = "manual",
    ) -> DispatchResult:
        """Выполняет цикл распределения очереди обращений линии поддержки на свободных операторов.

        Шаги алгоритма:
        1. Захватывает распределенную блокировку lock:dispatch:line:{line_code} в Redis на 5 секунд.
           Если линия уже обрабатывается параллельным процессом, завершается со статусом lock_busy.
        2. Проверяет наличие линии поддержки по ее коду в базе данных.
           Если линия не найдена, завершается со статусом line_not_found.
        3. В непрерывном цикле извлекает обращения из головы очереди Redis (LPOP):
           - Если очередь пуста, завершает цикл со статусом queue_empty.
           - Пытается атомарно назначить тикет через балансировщик (TicketBalancer.assign_ticket).
           - При непредвиденном сбое возвращает тикет в голову очереди (requeue_to_head) и пробрасывает ошибку.
           - При успешном назначении фиксирует тикет и продолжает цикл.
           - Если доступные операторы исчерпаны (no_operators_available), возвращает тикет в начало
             очереди Redis через LPUSH (requeue_to_head) и завершает цикл со статусом no_operators.
           - Если тикет не найден или не находится в статусе queued (например, закрыт/отменен),
             пропускает его и продолжает обработку оставшейся очереди.
        4. По выходу из контекстного менеджера блокировка Redis безопасно снимается Lua-скриптом.
        """
        logger.info(
            "Запуск цикла распределения линии %s (причина: %s)",
            line_code,
            trigger_reason,
        )
        lock = self.line_queue.get_dispatch_lock(line_code, ttl_seconds=5)

        async with lock as acquired:
            if not acquired:
                logger.info(
                    "Линия %s уже распределяется другим процессом (блокировка занята)",
                    line_code,
                )
                return DispatchResult(
                    line_code=line_code,
                    assigned_count=0,
                    assigned_ticket_ids=[],
                    stop_reason="lock_busy",
                )

            support_line = await self.support_line_repo.get_by_code(line_code)
            if support_line is None:
                logger.warning(
                    "Линия поддержки с кодом %s не найдена в базе данных",
                    line_code,
                )
                return DispatchResult(
                    line_code=line_code,
                    assigned_count=0,
                    assigned_ticket_ids=[],
                    stop_reason="line_not_found",
                )

            assigned_ticket_ids: list[UUID] = []
            stop_reason: Literal[
                "queue_empty", "no_operators", "lock_busy", "line_not_found"
            ] = "queue_empty"

            while True:
                raw_ticket_id = await self.line_queue.dequeue_ticket(line_code)
                if raw_ticket_id is None:
                    stop_reason = "queue_empty"
                    break

                try:
                    ticket_id = UUID(raw_ticket_id)
                except (ValueError, TypeError):
                    logger.warning(
                        "Некорректный формат UUID тикета в очереди линии %s: %r",
                        line_code,
                        raw_ticket_id,
                    )
                    continue

                try:
                    assignment = await self.balancer.assign_ticket(
                        ticket_id=ticket_id,
                        line_id=support_line.id,
                        auto_commit=True,
                    )
                except Exception:
                    logger.exception(
                        "Непредвиденный сбой при назначении тикета %s на линии %s. "
                        "Возврат тикета в голову очереди Redis.",
                        ticket_id,
                        line_code,
                    )
                    await self.line_queue.requeue_to_head(line_code, ticket_id)
                    raise

                if assignment.success:
                    assigned_ticket_ids.append(ticket_id)
                    logger.info(
                        "Тикет %s успешно назначен оператору %s на линии %s",
                        ticket_id,
                        assignment.operator.user_id
                        if assignment.operator
                        else None,
                        line_code,
                    )
                    continue

                if assignment.reason == "no_operators_available":
                    await self.line_queue.requeue_to_head(line_code, ticket_id)
                    logger.info(
                        "Свободные операторы на линии %s исчерпаны. "
                        "Тикет %s возвращен в начало очереди Redis.",
                        line_code,
                        ticket_id,
                    )
                    stop_reason = "no_operators"
                    break

                logger.info(
                    "Тикет %s пропущен при распределении линии %s (причина: %s)",
                    ticket_id,
                    line_code,
                    assignment.reason,
                )

            return DispatchResult(
                line_code=line_code,
                assigned_count=len(assigned_ticket_ids),
                assigned_ticket_ids=assigned_ticket_ids,
                stop_reason=stop_reason,
            )

    async def _safe_dispatch_task(
        self, line_code: str, trigger_reason: DispatchTriggerReason | str
    ) -> None:
        """Безопасно ставит задачу dispatch_line_queue в очередь Taskiq."""
        try:
            from src.operators.tasks import dispatch_line_queue

            await dispatch_line_queue.kiq(
                DispatchPayloadSchema(
                    line_code=line_code,
                    trigger_reason=trigger_reason,
                )
            )
        except Exception:
            logger.exception(
                "Не удалось поставить задачу dispatch_line_queue для линии %s (причина: %s)",
                line_code,
                trigger_reason,
            )

    async def _safe_copilot_task(self, ticket_id: UUID) -> None:
        """Безопасно ставит задачу generate_copilot_summary в очередь Taskiq."""
        try:
            from src.rag.schemas import CopilotPayloadSchema
            from src.rag.tasks import generate_copilot_summary

            await generate_copilot_summary.kiq(
                CopilotPayloadSchema(ticket_id=ticket_id)
            )
        except Exception:
            logger.exception(
                "Не удалось поставить задачу generate_copilot_summary для тикета %s",
                ticket_id,
            )

    async def get_profile(
        self, user_id: UUID
    ) -> OperatorProfileResponseSchema:
        """Возвращает параметры текущей смены оператора и количество активных слотов."""
        stats = await self.operator_repo.get_operator_profile_with_stats(
            user_id
        )
        if stats is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль оператора не найден",
            )
        profile, line_code, active_slots_count = stats
        full_name = (
            (profile.user.full_name or profile.user.email)
            if profile.user
            else ""
        )
        return OperatorProfileResponseSchema(
            user_id=profile.user_id,
            full_name=full_name,
            line_id=profile.line_id,
            line_code=line_code,
            shift_status=profile.shift_status,
            max_slots=profile.max_slots,
            active_slots_count=active_slots_count,
        )

    async def update_shift(
        self, user_id: UUID, shift_status: str
    ) -> OperatorProfileResponseSchema:
        """Обновляет статус рабочей смены оператора и инициирует диспетчеризацию при выходе на линию."""
        valid_statuses = {s.value for s in OperatorShiftStatus}
        if shift_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Недопустимый статус смены: {shift_status!r}. "
                    f"Допустимые значения: {sorted(valid_statuses)}"
                ),
            )

        profile = await self.operator_repo.update_shift_status(
            user_id, shift_status
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль оператора не найден",
            )
        await self.session.commit()

        if shift_status == OperatorShiftStatus.ACTIVE.value:
            line = await self.support_line_repo.get_by_id(profile.line_id)
            if line:
                await self._safe_dispatch_task(line.code, "shift_resumed")

        return await self.get_profile(user_id)

    async def get_sidebar_tickets(
        self, user_id: UUID
    ) -> list[OperatorSidebarTicketSchema]:
        """Возвращает список обращений, закрепленных за оператором в статусах assigned и in_progress."""
        tickets = await self.operator_repo.get_sidebar_tickets(user_id)
        result: list[OperatorSidebarTicketSchema] = []
        for t in tickets:
            client = t.chat.client if t.chat else None
            client_profile = client.client_profile if client else None
            last_msg = (
                max(t.messages, key=lambda m: m.created_at).text
                if t.messages
                else None
            )
            unread_count = sum(
                1
                for m in t.messages
                if m.sender_type == MessageSenderType.CLIENT.value
            )
            result.append(
                OperatorSidebarTicketSchema(
                    ticket_id=t.id,
                    chat_id=t.chat_id,
                    priority=t.priority,
                    status=str(t.status),
                    line_code=t.line.code if t.line else None,
                    client_name=(client.full_name or client.email)
                    if client
                    else None,
                    company_name=client_profile.company_name
                    if client_profile
                    else None,
                    last_message_preview=last_msg[:100] if last_msg else None,
                    unread_messages_count=unread_count,
                    created_at=t.created_at,
                    assigned_at=t.assigned_at,
                )
            )
        return result

    async def open_ticket(
        self, user_id: UUID, ticket_id: UUID
    ) -> OperatorTicketWorkspaceSchema:
        """Открывает карточку обращения, переводит в in_progress и возвращает полный контекст."""
        ticket = await self.operator_repo.get_ticket_workspace_data(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        if ticket.assigned_operator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Обращение закреплено за другим специалистом",
            )
        if ticket.status in TERMINAL_TICKET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Обращение уже закрыто",
            )

        # Идемпотентность: переводим в in_progress только если было assigned
        if ticket.status == TicketStatus.ASSIGNED.value:
            await self.operator_repo.assign_ticket_to_operator(
                ticket.id, user_id, status=TicketStatus.IN_PROGRESS.value
            )
            ticket.status = TicketStatus.IN_PROGRESS.value
            await self.session.commit()

            profile = await self.operator_repo.get_by_user_id(
                user_id, load_relations=True
            )
            operator_name = (
                (profile.user.full_name or profile.user.email)
                if profile and profile.user
                else "Оператор"
            )
            await self.ticket_events.publish_operator_joined(
                ticket_id=ticket.id, operator_name=operator_name
            )

        client = ticket.chat.client if ticket.chat else None
        client_profile = client.client_profile if client else None
        client_info = ClientInfoSchema(
            company_name=client_profile.company_name
            if client_profile
            else None,
            inn=client_profile.inn if client_profile else None,
            kpp=client_profile.kpp if client_profile else None,
            phone=client_profile.phone if client_profile else None,
            full_name=client.full_name if client else None,
            email=client.email if client else "",
        )
        messages_dto = [
            MessageResponseSchema.model_validate(m) for m in ticket.messages
        ]

        copilot_dto = (
            CopilotSummaryResponseSchema.model_validate(ticket.copilot_summary)
            if getattr(ticket, "copilot_summary", None) is not None
            else None
        )

        return OperatorTicketWorkspaceSchema(
            ticket_id=ticket.id,
            chat_id=ticket.chat_id,
            priority=ticket.priority,
            status=str(ticket.status),
            line_code=ticket.line.code if ticket.line else "",
            transfer_comment=ticket.transfer_comment,
            client=client_info,
            copilot_summary=copilot_dto,
            messages=messages_dto,
        )

    async def send_message(
        self, user_id: UUID, ticket_id: UUID, text: str
    ) -> MessageResponseSchema:
        """Отправляет текстовый ответ клиенту оператором с валидацией модератором."""
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        if ticket.assigned_operator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Обращение закреплено за другим специалистом",
            )
        if ticket.status != TicketStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Отправка сообщений разрешена только для обращений в статусе in_progress",
            )

        try:
            self.moderator.validate_operator_message(text)
        except ProfanityValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Сообщение содержит недопустимую лексику: {exc}",
            ) from exc

        msg = await self.operator_repo.save_operator_message(
            ticket_id=ticket.id, operator_id=user_id, text=text
        )
        operator_name = (
            ticket.assigned_operator.full_name
            if ticket.assigned_operator and ticket.assigned_operator.full_name
            else "Оператор поддержки"
        )
        operator_role = (
            ticket.assigned_operator.role.code
            if ticket.assigned_operator and ticket.assigned_operator.role
            else "operator"
        )
        msg_dto = MessageResponseSchema(
            id=msg.id,
            ticket_id=msg.ticket_id,
            sender_type=str(msg.sender_type),
            sender_id=msg.sender_id,
            sender_name=operator_name,
            sender_role=operator_role,
            text=msg.text,
            moderation_status=str(msg.moderation_status),
            sources=[],
            created_at=msg.created_at,
        )
        await self.session.commit()

        await self.chat_context.add_message(
            ticket_id=ticket.id,
            sender=MessageSenderType.OPERATOR.value,
            text=text,
            timestamp=msg_dto.created_at,
        )

        await self.ticket_events.publish_new_message(ticket.id, msg_dto)
        return msg_dto

    async def transfer_ticket(
        self,
        user_id: UUID,
        ticket_id: UUID,
        target_line_code: str,
        transfer_comment: str | None = None,
    ) -> TransferTicketResponseSchema:
        """Переводит обращение на другую линию поддержки и инициирует балансировку очередей."""
        ticket = await self.operator_repo.get_ticket_workspace_data(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        if ticket.assigned_operator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Перевод доступен только для закрепленного за вами обращения",
            )
        if ticket.status in TERMINAL_TICKET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя перевести уже закрытое обращение",
            )

        target_line = await self.support_line_repo.get_by_code(
            target_line_code
        )
        if target_line is None or not target_line.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Целевая линия поддержки '{target_line_code}' не найдена или неактивна",
            )

        current_line_code = ticket.line.code if ticket.line else None
        if current_line_code == target_line_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Обращение уже находится на линии {target_line_code}",
            )

        await self.operator_repo.transfer_ticket(
            ticket_id=ticket.id,
            target_line_id=target_line.id,
            comment=transfer_comment,
        )
        sys_text = (
            f"Обращение переведено на линию {target_line_code}: "
            f"{transfer_comment or 'без комментария'}"
        )
        await self.operator_repo.add_system_message(ticket.id, sys_text)
        await self.session.commit()

        await self.line_queue.enqueue_ticket(
            line_code=target_line_code,
            ticket_id=ticket.id,
            priority=ticket.priority,
        )

        await self.ticket_events.publish_ticket_transferred(
            ticket_id=ticket.id,
            new_line_code=target_line_code,
            reason=transfer_comment,
        )

        await self._safe_dispatch_task(target_line_code, "ticket_escalated")
        if current_line_code:
            await self._safe_dispatch_task(current_line_code, "slot_freed")

        await self._safe_copilot_task(ticket.id)

        return TransferTicketResponseSchema(
            status="queued",
            ticket_id=ticket.id,
            line_code=target_line_code,
        )

    async def resolve_ticket(
        self, user_id: UUID, ticket_id: UUID
    ) -> ResolveTicketResponseSchema:
        """Завершает обращение, освобождает слот оператора и запускает распределение линии."""
        ticket = await self.operator_repo.get_ticket_workspace_data(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )
        if ticket.assigned_operator_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Завершение доступно только для закрепленного за вами обращения",
            )
        if ticket.status in TERMINAL_TICKET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Обращение уже завершено",
            )

        closed_at = datetime.now(settings.TIMEZONE)
        await self.operator_repo.resolve_ticket(ticket.id)
        current_line_code = ticket.line.code if ticket.line else None
        await self.session.commit()

        await self.chat_context.clear_context(ticket.id)
        await self.ticket_events.publish_ticket_resolved(
            ticket_id=ticket.id,
            operator_id=user_id,
            closed_at=closed_at,
        )

        if current_line_code:
            await self._safe_dispatch_task(current_line_code, "slot_freed")

        return ResolveTicketResponseSchema(
            status="resolved",
            ticket_id=ticket.id,
            closed_at=closed_at,
        )

    async def handle_operator_connect(self, operator_id: UUID) -> None:
        """Фиксирует подключение оператора к SSE: инкрементирует счетчик и сбрасывает disconnected_at."""
        await self.redis_events.incr_operator_connections(operator_id)
        await self.operator_repo.mark_connected(operator_id)
        await self.session.commit()

    async def handle_operator_disconnect(self, operator_id: UUID) -> None:
        """Фиксирует отключение оператора: декрементирует счетчик и выставляет disconnected_at при <= 0."""
        try:
            remaining = await self.redis_events.decr_operator_connections(
                operator_id
            )
            if remaining <= 0:
                async with async_session_maker() as cleanup_session:
                    repo = OperatorRepository(cleanup_session)
                    await repo.mark_disconnected(operator_id)
                    await cleanup_session.commit()
        except Exception:
            pass

    async def stream_operator_events(
        self, operator_id: UUID, request: Request
    ) -> AsyncGenerator[str, None]:
        """Оркестрирует SSE-поток событий оператора с контролем жизненного цикла связи."""
        await self.handle_operator_connect(operator_id)
        # Освобождаем сессию в пул соединений на время долгоживущего потока Redis
        await self.session.close()
        try:
            async for chunk in self.redis_events.subscribe_operator_events(
                operator_id=operator_id, request=request
            ):
                yield chunk
        finally:
            try:
                await asyncio.shield(
                    self.handle_operator_disconnect(operator_id)
                )
            except (asyncio.CancelledError, Exception):
                pass

    async def check_timeouts(
        self, now: datetime | None = None
    ) -> CheckTimeoutsResult:
        """Централизованная проверка таймаутов неактивности и контроля связи операторов.

        Выполняет 3 независимых блока регламентных проверок:
        1. Неактивность клиента в диалоге с ботом (10 минут):
           - Тикеты со статусом bot_processing и updated_at <= now - 10 min.
           - Атомарный перевод в closed_by_inactivity через close_ticket_by_inactivity.
           - Очистка chat:context:{ticket_id} в Redis.
           - Добавление системного сообщения и публикация ticket_closed_inactivity.
        2. Неактивность клиента в диалоге с оператором (10 и 15 минут):
           - Тикеты со статусом in_progress.
           - Если последняя реплика от оператора и прошло >= 10 минут:
             отправка системного напоминания «Вы еще здесь?» (ровно 1 раз, исключая спам).
           - Если последняя реплика — системное напоминание («Вы еще здесь?») и прошло >= 5 минут
             (суммарно >= 15 минут без ответа клиента):
             атомарный перевод в closed_by_inactivity, очистка контекста, публикация события,
             освобождение слота оператора и запуск dispatch_line_queue для освободившегося слота.
        3. Контроль связи операторов (10 минут разрыва):
           - Операторы со статусом смены active/break и disconnected_at <= now - 10 min.
           - Перевод профиля в offline, сброс disconnected_at.
           - Массовый возврат активных тикетов оператора в queued (с сохранением line).
           - Возврат тикетов в начало очереди Redis соответствующей линии: LPUSH queue:line:{line_code}.
           - Запуск dispatch_line_queue ровно один раз на каждую затронутую линию (set(affected_lines)).
        """
        current_time = now or datetime.now(settings.TIMEZONE)

        bot_tickets_closed = 0
        operator_warnings_sent = 0
        operator_tickets_closed = 0
        operators_marked_offline = 0
        tickets_requeued = 0
        affected_line_codes: set[str] = set()

        # =========================================================================
        # 1. Неактивность клиента у бота (10 минут)
        # =========================================================================
        bot_cutoff = current_time - timedelta(minutes=10)
        inactive_bot_tickets = await self.ticket_repo.get_inactive_bot_tickets(
            cutoff=bot_cutoff, limit=100
        )
        for ticket in inactive_bot_tickets:
            closed = await self.ticket_repo.close_ticket_by_inactivity(
                ticket_id=ticket.id,
                cutoff=bot_cutoff,
                now=current_time,
            )
            if closed:
                await self.operator_repo.add_system_message(
                    ticket_id=ticket.id,
                    text="Диалог завершен в связи с отсутствием активности.",
                )
                await self.chat_context.clear_context(ticket.id)
                await self.ticket_events.publish_ticket_closed_inactivity(
                    ticket.id
                )
                bot_tickets_closed += 1

        # =========================================================================
        # 2. Неактивность клиента у оператора (10 минут напоминание, 15 минут закрытие)
        # =========================================================================
        warn_cutoff = current_time - timedelta(minutes=10)
        close_cutoff_5m = current_time - timedelta(minutes=5)

        in_progress_tickets = (
            await self.ticket_repo.get_in_progress_tickets_with_messages(
                limit=100
            )
        )
        for ticket in in_progress_tickets:
            if not ticket.messages:
                continue

            last_msg = max(ticket.messages, key=lambda m: m.created_at)

            # Шаг 1: Напоминание «Вы еще здесь?», если клиент молчит >= 10 минут после реплики оператора
            if (
                last_msg.sender_type == MessageSenderType.OPERATOR.value
                and last_msg.created_at <= warn_cutoff
            ):
                sys_msg = await self.operator_repo.add_system_message(
                    ticket_id=ticket.id,
                    text="Вы еще здесь?",
                )
                sys_dto = MessageResponseSchema(
                    id=sys_msg.id,
                    ticket_id=sys_msg.ticket_id,
                    sender_type=str(sys_msg.sender_type),
                    sender_id=sys_msg.sender_id,
                    text=sys_msg.text,
                    moderation_status=str(sys_msg.moderation_status),
                    sources=[],
                    created_at=sys_msg.created_at,
                )
                ticket.updated_at = current_time
                await self.ticket_events.publish_new_message(
                    ticket_id=ticket.id,
                    message_data=sys_dto,
                )
                operator_warnings_sent += 1

            # Шаг 2: Принудительное закрытие, если после напоминания клиент молчит >= 5 минут (суммарно >= 15 мин)
            elif (
                last_msg.sender_type == MessageSenderType.SYSTEM.value
                and last_msg.text == "Вы еще здесь?"
                and last_msg.created_at <= close_cutoff_5m
            ):
                closed = await self.ticket_repo.close_ticket_by_inactivity(
                    ticket_id=ticket.id,
                    cutoff=close_cutoff_5m,
                    now=current_time,
                )
                if closed:
                    await self.chat_context.clear_context(ticket.id)
                    await self.ticket_events.publish_ticket_closed_inactivity(
                        ticket.id
                    )
                    operator_tickets_closed += 1
                    line_code = ticket.line.code if ticket.line else None
                    if line_code:
                        affected_line_codes.add(line_code)

        # =========================================================================
        # 3. Контроль связи операторов (10 минут разрыва)
        # =========================================================================
        disconnect_cutoff = current_time - timedelta(minutes=10)
        disconnected_ops = await self.operator_repo.get_disconnected_operators(
            cutoff=disconnect_cutoff, limit=100
        )
        for op in disconnected_ops:
            await self.operator_repo.set_operator_offline(
                op.user_id, current_time
            )
            operators_marked_offline += 1

            requeued = await self.operator_repo.requeue_operator_tickets(
                operator_id=op.user_id, now=current_time
            )
            for t in requeued:
                tickets_requeued += 1
                if t.line and t.line.code:
                    await self.line_queue.requeue_to_head(
                        line_code=t.line.code, ticket_id=t.id
                    )
                    affected_line_codes.add(t.line.code)

        # =========================================================================
        # 4. Запуск контроля качества без отзыва клиента (10 минут)
        # =========================================================================
        audit_cutoff_10m = current_time - timedelta(minutes=10)
        unaudited_tickets = (
            await self.ticket_repo.get_tickets_for_audit_timeout(
                cutoff=audit_cutoff_10m, limit=100
            )
        )
        tickets_sent_to_audit = 0
        for ticket in unaudited_tickets:
            await self._safe_enqueue_audit(ticket.id, "feedback_timeout")
            tickets_sent_to_audit += 1

        # =========================================================================
        # 5. Фоновая сверка очередей ожидания (Reconciliation)
        # =========================================================================
        counts_by_line = (
            await self.operator_repo.count_queued_tickets_by_lines()
        )
        all_lines = await self.support_line_repo.get_all_active()
        for line in all_lines:
            expected_count = counts_by_line.get(line.id, 0)
            actual_count = await self.line_queue.get_queue_len(line.code)
            if expected_count != actual_count:
                logger.warning(
                    "Обнаружена рассинхронизация очереди линии %s: в БД=%d, в Redis=%d. Запуск восстановления.",
                    line.code,
                    expected_count,
                    actual_count,
                )
                dispatch_lock = self.line_queue.get_dispatch_lock(
                    line.code, ttl_seconds=10
                )
                async with dispatch_lock as line_locked:
                    if line_locked:
                        tickets = await self.operator_repo.get_queued_tickets_for_line(
                            line.id
                        )
                        ticket_ids = [t.id for t in tickets]
                        await self.line_queue.rebuild_line_queue(
                            line.code, ticket_ids
                        )
                        if ticket_ids:
                            affected_line_codes.add(line.code)

        # Коммит всех изменений в БД
        await self.session.commit()

        # Триггерим диспетчеризацию ровно один раз на каждую затронутую линию
        for line_code in affected_line_codes:
            await self._safe_dispatch_task(
                line_code=line_code, trigger_reason="operator_disconnected"
            )

        return CheckTimeoutsResult(
            bot_tickets_closed=bot_tickets_closed,
            operator_warnings_sent=operator_warnings_sent,
            operator_tickets_closed=operator_tickets_closed,
            operators_marked_offline=operators_marked_offline,
            tickets_requeued=tickets_requeued,
            tickets_sent_to_audit=tickets_sent_to_audit,
            affected_line_codes=sorted(affected_line_codes),
        )

    async def recover_queued_tickets_from_db(self) -> dict[str, Any]:
        """Аварийно восстанавливает очереди ожидания всех линий из PostgreSQL в Redis.

        Защищено глобальной блокировкой lock:queue_recovery на 30 секунд.
        Для каждой активной линии:
          1. Захватывает распределенную блокировку балансировщика lock:dispatch:line:{line_code}.
          2. Выбирает из БД тикеты со статусом queued с сортировкой priority ASC, created_at ASC
             (используя частичный индекс idx_tickets_queued_recovery).
          3. Перезаливает очередь в Redis через атомарный pipeline (DEL + RPUSH).
          4. Если в очереди есть тикеты, инициирует фоновую диспетчеризацию.
        """
        recovery_lock = self.line_queue.get_recovery_lock(ttl_seconds=30)
        async with recovery_lock as acquired:
            if not acquired:
                logger.info(
                    "recover_queued_tickets_from_db: распределенный лок recovery занят другим процессом, пропуск"
                )
                return {"status": "skipped", "reason": "already_recovering"}

            lines = await self.support_line_repo.get_all_active()
            recovered_lines: dict[str, int] = {}

            for line in lines:
                dispatch_lock = self.line_queue.get_dispatch_lock(
                    line.code, ttl_seconds=10
                )
                async with dispatch_lock as line_locked:
                    if not line_locked:
                        logger.warning(
                            "recover_queued_tickets_from_db: лок линии %s занят, пропуск линии",
                            line.code,
                        )
                        continue

                    tickets = (
                        await self.operator_repo.get_queued_tickets_for_line(
                            line.id
                        )
                    )
                    ticket_ids = [t.id for t in tickets]
                    await self.line_queue.rebuild_line_queue(
                        line.code, ticket_ids
                    )
                    recovered_lines[line.code] = len(ticket_ids)

                    if ticket_ids:
                        await self._safe_dispatch_task(
                            line.code, "queue_recovered"
                        )

            logger.info(
                "recover_queued_tickets_from_db успешно завершено: %s",
                recovered_lines,
            )
            return {
                "status": "success",
                "recovered_lines": recovered_lines,
            }

    async def _safe_enqueue_audit(
        self, ticket_id: UUID, trigger_reason: str
    ) -> None:
        """Безопасно ставит задачу audit_ticket_quality в очередь Taskiq."""
        try:
            from src.analytics.tasks import audit_ticket_quality

            await audit_ticket_quality.kiq(
                {
                    "ticket_id": str(ticket_id),
                    "trigger_reason": trigger_reason,
                }
            )
            logger.info(
                "Задача audit_ticket_quality для тикета %s поставлена в очередь (%s)",
                ticket_id,
                trigger_reason,
            )
        except Exception as exc:
            logger.warning(
                "Брокер Taskiq недоступен, задача аудита для тикета %s отложена: %s",
                ticket_id,
                exc,
            )
