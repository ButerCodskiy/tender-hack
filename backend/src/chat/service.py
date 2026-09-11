import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

import uuid6
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    MessageSourceModel,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.moderation import (
    ProfanityModerator,
    get_moderator,
)
from src.chat.repository import ChatRepository, TicketRepository
from src.chat.schemas import (
    ActiveTicketSummarySchema,
    CancelTicketResponseSchema,
    ChatStateResponseSchema,
    ClientResolveTicketResponseSchema,
    ClientSendMessageRequestSchema,
    EscalateRequestSchema,
    MessageResponseSchema,
)
from src.core.config import settings
from src.core.redis_client import (
    RedisChatContext,
    RedisLineQueue,
    RedisTicketEvents,
)
from src.rag.schemas import (
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagQueryRequestSchema,
    RagSourceChunkSchema,
    RagSourcesEventSchema,
)
from src.rag.service import RagService

logger = logging.getLogger(__name__)


class ChatService:
    """Сервис управления перепиской клиентов и оркестрации диалога."""

    def __init__(
        self,
        repo: ChatRepository,
        session: AsyncSession,
        rag_service: RagService,
        ticket_repo: TicketRepository | None = None,
        redis_context: RedisChatContext | None = None,
        moderator: ProfanityModerator | None = None,
        ticket_events: RedisTicketEvents | None = None,
        line_queue: RedisLineQueue | None = None,
    ) -> None:
        """Инициализирует сервис диалогов репозиториями, сессией БД, поисковым ядром и Redis."""
        self.repo = repo
        self.session = session
        self.rag_service = rag_service
        self.ticket_repo = ticket_repo or TicketRepository(session)
        self.redis_context = redis_context
        self.moderator = moderator or get_moderator()
        self.ticket_events = ticket_events
        self.line_queue = line_queue

    async def get_chat_state(self, user: UserModel) -> ChatStateResponseSchema:
        """Возвращает текущее состояние переписки и историю сообщений клиента.

        Метод находит постоянный чат клиента (или создает его при первом обращении),
        загружает активное обращение с назначенным оператором и линией поддержки,
        извлекает до 50 последних реплик ленты в хронологическом порядке и вычисляет
        флаги доступных клиенту действий.
        """
        chat = await self.repo.get_by_client_id(user.id)
        if chat is None:
            chat = ChatModel(client_id=user.id)
            await self.repo.create(chat)

        active_ticket = await self.ticket_repo.get_active_by_chat_id(chat.id)

        active_summary: ActiveTicketSummarySchema | None = None
        if active_ticket is not None:
            operator_name: str | None = None
            if active_ticket.assigned_operator is not None:
                operator_name = (
                    active_ticket.assigned_operator.full_name
                    or active_ticket.assigned_operator.email
                )
            line_code = (
                active_ticket.line.code
                if active_ticket.line is not None
                else None
            )
            active_summary = ActiveTicketSummarySchema(
                id=active_ticket.id,
                priority=active_ticket.priority,
                status=active_ticket.status,
                line_code=line_code,
                assigned_operator_name=operator_name,
                created_at=active_ticket.created_at,
            )

        recent_messages = await self.repo.get_recent_messages(
            chat.id, limit=50
        )
        messages_dto = [
            MessageResponseSchema.model_validate(msg)
            for msg in recent_messages
        ]

        can_escalate = bool(
            active_ticket
            and active_ticket.status == TicketStatus.BOT_PROCESSING
        )
        can_cancel = bool(
            active_ticket and active_ticket.status == TicketStatus.QUEUED
        )

        can_feedback = False
        feedback_ticket_id: UUID | None = None
        if active_ticket is None:
            last_closed = await self.ticket_repo.get_last_closed_by_chat_id(
                chat.id
            )
            if (
                last_closed is not None
                and last_closed.status == TicketStatus.RESOLVED
            ):
                can_feedback = True
                feedback_ticket_id = last_closed.id

        return ChatStateResponseSchema(
            chat_id=chat.id,
            active_ticket=active_summary,
            messages=messages_dto,
            can_escalate=can_escalate,
            can_cancel=can_cancel,
            can_feedback=can_feedback,
            feedback_ticket_id=feedback_ticket_id,
        )

    async def process_client_message(
        self,
        payload: ClientSendMessageRequestSchema,
        user: UserModel | None = None,
        client_id: UUID | None = None,
        accept_header: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Обрабатывает входящую реплику клиента и возвращает поток Server-Sent Events.

        1. Находит или создает постоянный чат клиента.
        2. Проверяет входящую реплику модератором ненормативной лексики.
        3. При обнаружении мата переводит обращение в closed_by_moderation, сохраняет реплику со статусом blocked,
           очищает оперативный контекст Redis и отдает SSE session_terminated либо HTTP 400.
        4. Если проверка пройдена, сохраняет реплику со статусом passed в messages и оперативный контекст Redis.
        5. Запускает генератор RagService.generate_answer.
        6. Отдает поток SSE со статусами, источниками, предложениями и финальным событием done.
        7. По завершении генерации фиксирует ответ бота и источники в PostgreSQL и Redis.
        """
        user_id = user.id if user is not None else client_id
        if user_id is None:
            raise ValueError(
                "Для обработки сообщения требуется передать пользователя"
            )

        chat = await self.repo.get_by_client_id(user_id)
        if chat is None:
            chat = ChatModel(client_id=user_id)
            await self.repo.create(chat)

        if payload.new_ticket:
            prev_active = await self.ticket_repo.get_active_by_chat_id(chat.id)
            if (
                prev_active
                and prev_active.status == TicketStatus.BOT_PROCESSING
            ):
                prev_active.status = TicketStatus.RESOLVED
                prev_active.closed_at = datetime.now(settings.TIMEZONE)
                await self.ticket_repo.update(prev_active)
            active_ticket = None
        elif payload.ticket_id:
            active_ticket = await self.ticket_repo.get_by_id(payload.ticket_id)
            if active_ticket and active_ticket.chat_id != chat.id:
                active_ticket = None
        else:
            active_ticket = await self.ticket_repo.get_active_by_chat_id(
                chat.id
            )

        # 1. Проверка модератором обсценной лексики
        moderation_result = self.moderator.check_profanity(payload.text)
        if moderation_result.is_profane:
            if active_ticket is None:
                active_ticket = TicketModel(
                    chat_id=chat.id,
                    status=TicketStatus.CLOSED_BY_MODERATION,
                    priority=TicketPriority.P2,
                    closed_at=datetime.now(settings.TIMEZONE),
                )
                await self.ticket_repo.create(active_ticket)
            else:
                active_ticket.status = TicketStatus.CLOSED_BY_MODERATION
                active_ticket.closed_at = datetime.now(settings.TIMEZONE)
                await self.ticket_repo.update(active_ticket)

            client_message = MessageModel(
                id=uuid6.uuid7(),
                ticket_id=active_ticket.id,
                sender_type=MessageSenderType.CLIENT,
                sender_id=user_id,
                text=payload.text,
                moderation_status=MessageModerationStatus.BLOCKED,
                moderation_reason=moderation_result.reason or "profanity",
                created_at=datetime.now(settings.TIMEZONE),
            )
            await self.repo.save_message(client_message)
            await self.session.commit()

            # Очищаем оперативный контекст диалога в Redis
            await self.redis_context.clear_context(active_ticket.id)

            termination_msg = (
                "Ваше обращение завершено в связи с нарушением правил общения "
                "(использование нецензурной лексики). Пожалуйста, сформируйте "
                "новое обращение в корректной форме."
            )

            if accept_header and "text/event-stream" in accept_header:
                event_data = json.dumps(
                    {
                        "reason": "profanity",
                        "message": termination_msg,
                    },
                    ensure_ascii=False,
                )
                yield f"event: session_terminated\ndata: {event_data}\n\n"
                return

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=termination_msg,
            )

        if active_ticket is None:
            active_ticket = TicketModel(
                chat_id=chat.id,
                status=TicketStatus.BOT_PROCESSING,
                priority=TicketPriority.P2,
            )
            await self.ticket_repo.create(active_ticket)

        client_message = MessageModel(
            id=uuid6.uuid7(),
            ticket_id=active_ticket.id,
            sender_type=MessageSenderType.CLIENT,
            sender_id=user_id,
            text=payload.text,
            moderation_status=MessageModerationStatus.PASSED,
            created_at=datetime.now(settings.TIMEZONE),
        )
        await self.repo.save_message(client_message)
        await self.session.commit()

        await self.redis_context.add_message(
            ticket_id=active_ticket.id,
            sender=MessageSenderType.CLIENT.value,
            text=payload.text,
            timestamp=client_message.created_at,
        )

        bot_message_id = uuid6.uuid7()
        rag_request = RagQueryRequestSchema(
            query=payload.text,
            message_id=bot_message_id,
        )

        collected_sources: list[RagSourceChunkSchema] = []

        try:
            async for event in self.rag_service.generate_answer(rag_request):
                if isinstance(event, RagSourcesEventSchema):
                    collected_sources.extend(event.sources)
                elif isinstance(event, RagDoneEventSchema):
                    target_bot_id = event.message_id or bot_message_id
                    bot_message = MessageModel(
                        id=target_bot_id,
                        ticket_id=active_ticket.id,
                        sender_type=MessageSenderType.BOT,
                        sender_id=None,
                        text=event.text,
                        moderation_status=MessageModerationStatus.PASSED,
                        created_at=datetime.now(settings.TIMEZONE),
                    )
                    source_models = [
                        MessageSourceModel(
                            id=uuid6.uuid7(),
                            message_id=target_bot_id,
                            chunk_id=src.chunk_id,
                            doc_id=src.doc_id,
                            quote_text=src.quote_text,
                            created_at=datetime.now(settings.TIMEZONE),
                        )
                        for src in collected_sources
                    ]
                    await self.repo.save_message(
                        bot_message, sources=source_models
                    )
                    await self.session.commit()

                    await self.redis_context.add_message(
                        ticket_id=active_ticket.id,
                        sender=MessageSenderType.BOT.value,
                        text=event.text,
                        timestamp=bot_message.created_at,
                    )
                elif isinstance(event, RagDegradedModeEventSchema):
                    target_bot_id = bot_message_id
                    bot_message = MessageModel(
                        id=target_bot_id,
                        ticket_id=active_ticket.id,
                        sender_type=MessageSenderType.BOT,
                        sender_id=None,
                        text=event.message,
                        moderation_status=MessageModerationStatus.PASSED,
                        created_at=datetime.now(settings.TIMEZONE),
                    )
                    source_models = [
                        MessageSourceModel(
                            id=uuid6.uuid7(),
                            message_id=target_bot_id,
                            chunk_id=src.chunk_id,
                            doc_id=src.doc_id,
                            quote_text=src.quote_text,
                            created_at=datetime.now(settings.TIMEZONE),
                        )
                        for src in (event.sources or collected_sources)
                    ]
                    await self.repo.save_message(
                        bot_message, sources=source_models
                    )
                    await self.session.commit()

                    await self.redis_context.add_message(
                        ticket_id=active_ticket.id,
                        sender=MessageSenderType.BOT.value,
                        text=event.message,
                        timestamp=bot_message.created_at,
                    )

                if isinstance(event, RagDoneEventSchema):
                    event.ticket_id = active_ticket.id
                data_json = event.model_dump_json(exclude={"event"})
                yield f"event: {event.event}\ndata: {data_json}\n\n"
        except Exception as exc:
            logger.warning(
                "Критический сбой конвейера RAG, переход в режим деградации: %s",
                exc,
            )
            fallback_text = (
                "Генеративная модель временно недоступна. "
                "Ниже представлены найденные нормативные регламенты."
            )
            degraded_event = RagDegradedModeEventSchema(
                message=fallback_text,
                sources=collected_sources,
            )
            bot_message = MessageModel(
                id=bot_message_id,
                ticket_id=active_ticket.id,
                sender_type=MessageSenderType.BOT,
                sender_id=None,
                text=fallback_text,
                moderation_status=MessageModerationStatus.PASSED,
                created_at=datetime.now(settings.TIMEZONE),
            )
            source_models = [
                MessageSourceModel(
                    id=uuid6.uuid7(),
                    message_id=bot_message_id,
                    chunk_id=src.chunk_id,
                    doc_id=src.doc_id,
                    quote_text=src.quote_text,
                    created_at=datetime.now(settings.TIMEZONE),
                )
                for src in collected_sources
            ]
            await self.repo.save_message(bot_message, sources=source_models)
            await self.session.commit()

            await self.redis_context.add_message(
                ticket_id=active_ticket.id,
                sender=MessageSenderType.BOT.value,
                text=fallback_text,
                timestamp=bot_message.created_at,
            )

            data_json = degraded_event.model_dump_json(exclude={"event"})
            yield f"event: {degraded_event.event}\ndata: {data_json}\n\n"

    async def send_operator_message(
        self,
        ticket_id: UUID,
        operator: UserModel,
        text: str,
    ) -> MessageModel:
        """Отправляет ответ оператора в чат с валидацией на ненормативную лексику.

        Raises:
            ProfanityValidationError: если обнаружен мат (преобразуется в HTTP 422).
            HTTPException: если тикет не найден (HTTP 404).
        """
        self.moderator.validate_operator_message(text)

        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )

        operator_message = MessageModel(
            id=uuid6.uuid7(),
            ticket_id=ticket.id,
            sender_type=MessageSenderType.OPERATOR,
            sender_id=operator.id,
            text=text,
            moderation_status=MessageModerationStatus.PASSED,
            created_at=datetime.now(settings.TIMEZONE),
        )
        await self.repo.save_message(operator_message)
        await self.session.commit()

        await self.redis_context.add_message(
            ticket_id=ticket.id,
            sender=MessageSenderType.OPERATOR.value,
            text=text,
            timestamp=operator_message.created_at,
        )
        return operator_message

    async def stream_chat_events(
        self,
        user: UserModel,
        ticket_id: UUID | None,
        request: Request,
        last_event_id: UUID | str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Оркестрирует поток Server-Sent Events для клиента по каналу обращения с поддержкой Replay."""
        if self.ticket_events is None:
            raise RuntimeError(
                "RedisTicketEvents не инициализирован в ChatService"
            )

        chat = await self.repo.get_by_client_id(user.id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "no_active_ticket",
                    "message": "Активное обращение не найдено",
                },
            )

        target_ticket_id: UUID
        if ticket_id is not None:
            ticket = await self.ticket_repo.get_by_id(ticket_id)
            if ticket is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Обращение не найдено",
                )
            if ticket.chat_id != chat.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Доступ к данному обращению запрещен",
                )
            target_ticket_id = ticket.id
        else:
            active_ticket = await self.ticket_repo.get_active_by_chat_id(
                chat.id
            )
            if active_ticket is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "no_active_ticket",
                        "message": "Активное обращение не найдено",
                    },
                )
            target_ticket_id = active_ticket.id

        seen_message_ids: set[str] = set()

        # Replay пропущенных сообщений по Last-Event-ID
        if last_event_id:
            parsed_event_id: UUID | None = None
            if isinstance(last_event_id, UUID):
                parsed_event_id = last_event_id
            elif isinstance(last_event_id, str):
                try:
                    parsed_event_id = UUID(last_event_id)
                except ValueError:
                    parsed_event_id = None

            if parsed_event_id:
                seen_message_ids.add(str(parsed_event_id))
                missed_messages = await self.repo.get_messages_since_id(
                    ticket_id=target_ticket_id,
                    last_event_id=parsed_event_id,
                )
                for msg in missed_messages:
                    seen_message_ids.add(str(msg.id))
                    msg_dto = MessageResponseSchema.model_validate(msg)
                    data_str = json.dumps(
                        msg_dto.model_dump(mode="json"),
                        ensure_ascii=False,
                        default=str,
                    )
                    yield f"id: {msg.id}\nevent: new_message\ndata: {data_str}\n\n"

        # Все выборки из БД завершены, дальше идет только Redis Pub/Sub.
        # Освобождаем сессию в пул соединений, чтобы не удерживать соединение с PostgreSQL.
        await self.session.close()

        async for chunk in self.ticket_events.subscribe_ticket_events(
            ticket_id=target_ticket_id, request=request
        ):
            if seen_message_ids:
                lines = chunk.splitlines()
                skip_chunk = False
                for line in lines:
                    if line.startswith("id: "):
                        ev_id = line[4:].strip()
                        if ev_id in seen_message_ids:
                            skip_chunk = True
                            break
                        seen_message_ids.add(ev_id)
                if skip_chunk:
                    continue

            yield chunk

    async def _safe_dispatch_task(
        self, line_code: str, trigger_reason: str
    ) -> None:
        """Безопасно ставит задачу dispatch_line_queue в очередь Taskiq."""
        try:
            from src.operators.schemas import DispatchPayloadSchema
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

    async def escalate_ticket(
        self,
        user: UserModel,
        payload: EscalateRequestSchema | None = None,
    ) -> ActiveTicketSummarySchema:
        """Переводит обращение клиента из bot_processing в queued к операторам."""
        chat = await self.repo.get_by_client_id(user.id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Чат клиента не найден",
            )

        active_ticket = await self.ticket_repo.get_active_by_chat_id(chat.id)
        if active_ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Активное обращение не найдено",
            )

        if active_ticket.status in (
            TicketStatus.QUEUED.value,
            TicketStatus.ASSIGNED.value,
            TicketStatus.IN_PROGRESS.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ticket_already_escalated",
                    "message": "Обращение уже находится в очереди или назначено оператору",
                },
            )

        line_code = "L1"
        if active_ticket.line is not None:
            line_code = active_ticket.line.code
        else:
            from src.operators.repository import SupportLineRepository

            line_repo = SupportLineRepository(self.session)
            l1_line = await line_repo.get_by_code(line_code)
            if l1_line is not None:
                active_ticket.line_id = l1_line.id

        now = datetime.now(settings.TIMEZONE)
        active_ticket.status = TicketStatus.QUEUED.value
        active_ticket.opened_at = now
        active_ticket.escalation_reason = (
            payload.reason
            if payload and payload.reason
            else "client_requested"
        )
        await self.ticket_repo.update(active_ticket)
        await self.session.commit()

        if self.line_queue is not None:
            await self.line_queue.enqueue_ticket(
                line_code=line_code,
                ticket_id=active_ticket.id,
                priority=active_ticket.priority,
            )

        await self._safe_dispatch_task(line_code, "ticket_escalated")
        await self._safe_copilot_task(active_ticket.id)

        operator_name: str | None = None
        if active_ticket.assigned_operator is not None:
            operator_name = (
                active_ticket.assigned_operator.full_name
                or active_ticket.assigned_operator.email
            )

        return ActiveTicketSummarySchema(
            id=active_ticket.id,
            priority=active_ticket.priority,
            status=active_ticket.status,
            line_code=line_code,
            assigned_operator_name=operator_name,
            created_at=active_ticket.created_at,
        )

    async def resolve_ticket_by_client(
        self,
        user: UserModel,
        ticket_id: UUID,
    ) -> ClientResolveTicketResponseSchema:
        """Подтверждает успешное решение вопроса клиентом."""
        chat = await self.repo.get_by_client_id(user.id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Чат клиента не найден",
            )

        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None or ticket.chat_id != chat.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )

        from src.chat.models import TERMINAL_TICKET_STATUSES

        if ticket.status in TERMINAL_TICKET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Обращение уже завершено",
            )

        now = datetime.now(settings.TIMEZONE)
        ticket.status = TicketStatus.RESOLVED.value
        ticket.closed_at = now
        await self.ticket_repo.update(ticket)
        await self.session.commit()

        if self.redis_context is not None:
            await self.redis_context.clear_context(ticket.id)

        if self.ticket_events is not None:
            await self.ticket_events.publish_ticket_resolved(
                ticket_id=ticket.id,
                operator_id=ticket.assigned_operator_id,
                closed_at=now,
            )

        if ticket.line is not None and ticket.assigned_operator_id is not None:
            await self._safe_dispatch_task(ticket.line.code, "slot_freed")

        return ClientResolveTicketResponseSchema(
            status="resolved",
            ticket_id=ticket.id,
            closed_at=now,
        )

    async def cancel_ticket_by_client(
        self,
        user: UserModel,
        ticket_id: UUID,
    ) -> CancelTicketResponseSchema:
        """Отменяет обращение клиентом до начала диалога с оператором."""
        chat = await self.repo.get_by_client_id(user.id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Чат клиента не найден",
            )

        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None or ticket.chat_id != chat.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )

        if ticket.status == TicketStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя отменить обращение, диалог по которому уже начат специалистом",
            )

        now = datetime.now(settings.TIMEZONE)
        ticket.status = TicketStatus.CANCELED.value
        ticket.closed_at = now
        assigned_op_id = ticket.assigned_operator_id
        ticket.assigned_operator_id = None
        await self.ticket_repo.update(ticket)
        await self.session.commit()

        if self.redis_context is not None:
            await self.redis_context.clear_context(ticket.id)

        if self.ticket_events is not None:
            await self.ticket_events.publish_ticket_resolved(
                ticket_id=ticket.id,
                operator_id=assigned_op_id,
                closed_at=now,
            )

        if ticket.line is not None and assigned_op_id is not None:
            await self._safe_dispatch_task(ticket.line.code, "slot_freed")

        return CancelTicketResponseSchema(
            status="canceled",
            ticket_id=ticket.id,
        )
