"""Балансировщик нагрузки и распределения обращений по операторам."""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.chat.models import TicketStatus
from src.chat.repository import TicketRepository
from src.core.config import settings
from src.core.redis_client import RedisOperatorEvents
from src.operators.models import OperatorProfileModel
from src.operators.repository import OperatorRepository
from src.operators.schemas import AssignmentResult, TicketAssignedDataSchema

logger = logging.getLogger(__name__)


class TicketBalancer:
    """Балансировщик распределения тикетов на наименее загруженных операторов."""

    def __init__(
        self,
        session: AsyncSession,
        redis_events: RedisOperatorEvents | None = None,
        ticket_repo: TicketRepository | None = None,
        operator_repo: OperatorRepository | None = None,
    ) -> None:
        """Инициализирует балансировщик сессией базы данных, репозиториями и шиной событий."""
        self.session = session
        self.redis_events = redis_events
        self.ticket_repo = ticket_repo or TicketRepository(session)
        self.operator_repo = operator_repo or OperatorRepository(session)

    async def find_available_operator(
        self, line_id: int
    ) -> OperatorProfileModel | None:
        """Делегирует атомарный выбор наименее загруженного оператора репозиторию."""
        return await self.operator_repo.get_least_loaded_active_for_update(
            line_id
        )

    async def assign_ticket(
        self,
        ticket_id: UUID,
        line_id: int | None = None,
        auto_commit: bool = True,
    ) -> AssignmentResult:
        """Выполняет атомарное закрепление тикета за оператором с оповещением через шину.

        Алгоритм:
        1. Блокирует строку тикета в базе данных через TicketRepository.get_by_id_for_update.
        2. Проверяет, что обращение находится в статусе queued.
        3. Находит наименее загруженного оператора на линии через OperatorRepository.
        4. При отсутствии операторов возвращает результат с причиной no_operators_available.
        5. При нахождении оператора переводит тикет в assigned, заполняет assigned_operator_id,
           фиксирует assigned_at и обновляет last_assigned_at оператора.
        6. Фиксирует транзакцию (commit при auto_commit=True).
        7. Публикует событие ticket_assigned в канал Redis channel:operator:{operator_id}.
        """
        ticket = await self.ticket_repo.get_by_id_for_update(
            ticket_id, load_details=True
        )

        if ticket is None:
            return AssignmentResult(
                success=False,
                reason="ticket_not_found",
            )

        if ticket.status != TicketStatus.QUEUED:
            return AssignmentResult(
                success=False,
                ticket=ticket,
                reason="ticket_not_queued",
            )

        target_line_id = line_id if line_id is not None else ticket.line_id
        if target_line_id is None:
            return AssignmentResult(
                success=False,
                ticket=ticket,
                reason="line_not_specified",
            )

        operator: OperatorProfileModel | None = None
        for _ in range(5):
            operator = await self.find_available_operator(target_line_id)
            if operator is not None:
                break
            await asyncio.sleep(0.02)

        if operator is None:
            return AssignmentResult(
                success=False,
                ticket=ticket,
                reason="no_operators_available",
            )

        now = datetime.now(settings.TIMEZONE)
        ticket.status = TicketStatus.ASSIGNED
        ticket.assigned_operator_id = operator.user_id
        ticket.assigned_at = now
        ticket.updated_at = now

        operator.last_assigned_at = now
        operator.updated_at = now

        if auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

        # Публикация события в Redis Pub/Sub после фиксации в базе данных
        if self.redis_events is not None:
            try:
                event_data = TicketAssignedDataSchema.from_ticket(ticket)
                await self.redis_events.publish_ticket_assigned(
                    operator.user_id, event_data
                )
            except Exception:
                logger.warning(
                    "Сбой отправки события ticket_assigned в Redis для оператора %s",
                    operator.user_id,
                    exc_info=True,
                )

        return AssignmentResult(
            success=True,
            operator=operator,
            ticket=ticket,
        )
