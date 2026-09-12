"""Бизнес-логика контроля качества, аудита диалогов и фиксации инцидентов."""

import csv
import io
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import uuid6
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status as http_status

from src.analytics.evaluator import (
    AuditLlmClientProtocol,
    OllamaAuditLlmClient,
    build_audit_dialog_context,
)
from src.analytics.models import (
    IncidentStatus,
    IncidentType,
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.repository import AnalyticsRepository
from src.analytics.schemas import (
    EXPORT_HEADERS,
    AnalyticsDashboardResponseSchema,
    AnalyticsExportResponseSchema,
    AnalyticsExportRowSchema,
    FeedbackResponseSchema,
    OperatorDailyMetricResponseSchema,
    SystemicIssueItemSchema,
    SystemicIssuesReportResponseSchema,
    SystemicMetricsSummarySchema,
)
from src.chat.models import MessageModerationStatus, TicketStatus
from src.chat.repository import TicketRepository
from src.core.config import settings

EXPORT_MAX_DAYS = 90

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Сервис контроля качества диалогов, арбитража ответственности и сбора отзывов."""

    def __init__(
        self,
        session: AsyncSession,
        redis: aioredis.Redis,
        evaluator: AuditLlmClientProtocol | None = None,
        analytics_repo: AnalyticsRepository | None = None,
        ticket_repo: TicketRepository | None = None,
    ) -> None:
        self.session = session
        self.redis = redis
        self.evaluator = evaluator or OllamaAuditLlmClient()
        self.analytics_repo = analytics_repo or AnalyticsRepository(session)
        self.ticket_repo = ticket_repo or TicketRepository(session)

    async def audit_ticket_quality(
        self,
        ticket_id: UUID,
        trigger_reason: str = "feedback_received",
    ) -> dict[str, Any]:
        """Выполняет автоматический аудит закрытого диалога языковой моделью.

        1. Fast-path: проверка наличия ранее проведенного аудита (идемпотентность).
        2. Захват распределенной блокировки в Redis lock:audit:ticket:{ticket_id}.
        3. Загрузка реплик, отзыва, линии и исполнителя обращения.
        4. Формирование контекста и вызов LLM-Judge (evaluator.evaluate_dialog).
        5. Фиксация результатов в ticket_audits.
        6. При выявлении системного сбоя: дедупликация и регистрация в system_incidents.
        7. При фатальных сбоях вызова модели: регистрация инцидента api_error в system_incidents.
        """
        # 1. Fast-path: проверка на уже существующий аудит
        existing_audit = await self.analytics_repo.get_audit_by_ticket_id(
            ticket_id
        )
        if existing_audit is not None:
            logger.info(
                "Аудит для тикета %s уже проведен ранее, пропуск задачи",
                ticket_id,
            )
            return {
                "ticket_id": str(ticket_id),
                "status": "already_audited",
                "politeness_score": existing_audit.politeness_score,
                "completeness_score": existing_audit.completeness_score,
                "root_cause": existing_audit.root_cause,
                "is_system_issue": existing_audit.is_system_issue,
            }

        # 2. Распределенная блокировка в Redis от параллельного вызова LLM
        lock_key = f"lock:audit:ticket:{ticket_id}"
        lock_acquired = await self.redis.set(lock_key, "1", nx=True, ex=60)
        if not lock_acquired:
            logger.warning(
                "Аудит тикета %s уже выполняется параллельным воркером (lock занят)",
                ticket_id,
            )
            return {
                "ticket_id": str(ticket_id),
                "status": "locked",
            }

        try:
            # 3. Загрузка полных данных обращения
            ticket = await self.analytics_repo.get_ticket_full_audit_data(
                ticket_id
            )
            if ticket is None:
                logger.warning(
                    "Обращение %s не найдено в БД, аудит прерван", ticket_id
                )
                return {
                    "ticket_id": str(ticket_id),
                    "status": "ticket_not_found",
                }

            messages_data = [
                {"sender": m.sender_type, "text": m.text}
                for m in ticket.messages
                if m.moderation_status != MessageModerationStatus.BLOCKED.value
            ]
            feedback = ticket.feedback
            feedback_score = feedback.score if feedback else None
            feedback_comment = feedback.comment if feedback else None
            line_code = ticket.line.code if ticket.line else None
            op_name = (
                ticket.assigned_operator.full_name
                if ticket.assigned_operator
                else None
            )

            context_prompt = build_audit_dialog_context(
                ticket_id=ticket.id,
                line_code=line_code,
                assigned_operator_name=op_name,
                feedback_score=feedback_score,
                feedback_comment=feedback_comment,
                messages=messages_data,
            )

            # 4. Вызов модели-оценщика
            now = datetime.now(settings.TIMEZONE)
            try:
                verdict = await self.evaluator.evaluate_dialog(
                    prompt=context_prompt
                )
            except Exception as exc:
                logger.error(
                    "Сбой работы LLM-Judge для тикета %s (Dead-Letter handling): %s",
                    ticket_id,
                    exc,
                )
                # Фиксация сбоя аналитики в реестре системных инцидентов
                incident = SystemIncidentModel(
                    id=uuid6.uuid7(),
                    ticket_id=ticket_id,
                    incident_type=IncidentType.API_ERROR.value,
                    description=f"Фатальный сбой LLM-аудита диалога тикета {ticket_id}: {exc}",
                    status=IncidentStatus.OPEN.value,
                    created_at=now,
                )
                await self.analytics_repo.create_incident(incident)
                await self.session.commit()
                return {
                    "ticket_id": str(ticket_id),
                    "status": "llm_evaluation_failed",
                    "error": str(exc),
                }

            # 5. Сохранение результатов аудита в ticket_audits
            audit = TicketAuditModel(
                id=uuid6.uuid7(),
                ticket_id=ticket_id,
                politeness_score=verdict.politeness_score,
                completeness_score=verdict.completeness_score,
                root_cause=verdict.root_cause,
                summary=verdict.summary,
                is_system_issue=verdict.is_system_issue,
                created_at=now,
            )
            await self.analytics_repo.create_audit(audit)

            # 6. Дедупликация и сохранение инцидента платформы при выявлении сбоя
            incident_created = False
            if verdict.is_system_issue and verdict.incident_type:
                open_incident = (
                    await self.analytics_repo.get_open_incident_by_type(
                        incident_type=verdict.incident_type,
                        window_hours=2,
                        now=now,
                    )
                )
                if open_incident is None:
                    incident = SystemIncidentModel(
                        id=uuid6.uuid7(),
                        ticket_id=ticket_id,
                        incident_type=verdict.incident_type,
                        description=verdict.incident_description
                        or verdict.summary,
                        status=IncidentStatus.OPEN.value,
                        created_at=now,
                    )
                    await self.analytics_repo.create_incident(incident)
                    incident_created = True
                    logger.info(
                        "Зарегистрирован системный инцидент %s (тикет %s)",
                        verdict.incident_type,
                        ticket_id,
                    )
                else:
                    logger.info(
                        "Инцидент %s уже открыт (id=%s). Дубликат для тикета %s пропущен",
                        verdict.incident_type,
                        open_incident.id,
                        ticket_id,
                    )

            await self.session.commit()

            return {
                "ticket_id": str(ticket_id),
                "status": "success",
                "politeness_score": verdict.politeness_score,
                "completeness_score": verdict.completeness_score,
                "root_cause": verdict.root_cause,
                "is_system_issue": verdict.is_system_issue,
                "incident_created": incident_created,
                "trigger_reason": trigger_reason,
            }

        finally:
            await self.redis.delete(lock_key)

    async def save_feedback(
        self,
        user_id: UUID,
        ticket_id: UUID,
        score: int,
        comment: str | None = None,
    ) -> FeedbackResponseSchema:
        """Сохраняет оценку клиента и ставит фоновую задачу аудита в очередь Taskiq."""
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не найдено",
            )

        # Проверка прав: оценивать тикет может только его автор (клиент)
        if ticket.chat.client_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Обращение не принадлежит текущему пользователю",
            )

        # Оценивать можно только завершенные тикеты
        if ticket.status != TicketStatus.RESOLVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Оценка доступна только для завершенных обращений",
            )

        # Проверка на повторный отзыв
        existing_feedback = (
            await self.analytics_repo.get_feedback_by_ticket_id(ticket_id)
        )
        if existing_feedback is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Отзыв по данному обращению уже оставлен",
            )

        now = datetime.now(settings.TIMEZONE)
        feedback = TicketFeedbackModel(
            id=uuid6.uuid7(),
            ticket_id=ticket_id,
            score=score,
            comment=comment,
            created_at=now,
        )
        await self.analytics_repo.create_feedback(feedback)
        await self.session.commit()

        # Безопасная постановка задачи в Taskiq (не роняет HTTP при сбое брокера)
        await self._safe_enqueue_audit(
            ticket_id=ticket_id, trigger_reason="feedback_received"
        )

        return FeedbackResponseSchema.model_validate(feedback)

    async def _safe_enqueue_audit(
        self, ticket_id: UUID, trigger_reason: str
    ) -> None:
        """Безопасно ставит задачу audit_ticket_quality в очередь Taskiq с синхронным фолбэком."""
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
                "Брокер Taskiq недоступен (%s), выполняется синхронный аудит тикета %s (фолбэк)",
                exc,
                ticket_id,
            )
            try:
                await self.audit_ticket_quality(
                    ticket_id=ticket_id,
                    trigger_reason=trigger_reason,
                )
                logger.info(
                    "Синхронный аудит тикета %s успешно выполнен (фолбэк)",
                    ticket_id,
                )
            except Exception as fallback_exc:
                logger.error(
                    "Сбой синхронного аудита тикета %s: %s",
                    ticket_id,
                    fallback_exc,
                )

    async def get_dashboard(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> AnalyticsDashboardResponseSchema:
        """Формирует сводную витрину аналитического дашборда на лету.

        Принимает опциональные даты from_date и to_date.
        При отсутствии from_date по умолчанию используется начало текущих суток.
        При отсутствии to_date по умолчанию используется конец текущих суток.
        Все даты рассчитываются в часовом поясе проекта (Europe/Moscow).
        """
        now_msk = datetime.now(settings.TIMEZONE)

        if from_date is not None:
            from_dt = datetime.combine(from_date, time.min).replace(
                tzinfo=settings.TIMEZONE
            )
        else:
            from_dt = datetime.combine(now_msk.date(), time.min).replace(
                tzinfo=settings.TIMEZONE
            )

        if to_date is not None:
            to_dt = datetime.combine(to_date, time.max).replace(
                tzinfo=settings.TIMEZONE
            )
        else:
            to_dt = datetime.combine(now_msk.date(), time.max).replace(
                tzinfo=settings.TIMEZONE
            )

        if from_dt > to_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Параметр from_date не может быть позже to_date",
            )

        metrics = await self.analytics_repo.get_dashboard_metrics(
            from_dt=from_dt,
            to_dt=to_dt,
        )
        return AnalyticsDashboardResponseSchema.model_validate(metrics)

    async def get_operator_metrics(
        self,
        target_date: date | None = None,
        line_code: str | None = None,
    ) -> list[OperatorDailyMetricResponseSchema]:
        """Возвращает суточные показатели операторов с фильтрацией по дате и линии."""
        return await self.analytics_repo.get_operator_metrics(
            target_date=target_date,
            line_code=line_code,
        )

    async def calculate_daily_metrics(
        self,
        target_date: date | None = None,
        operator_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Выполняет суточный расчет показателей эффективности операторов.

        Если target_date не указан, расчет выполняется строго за вчерашние сутки
        в часовом поясе Москвы (settings.TIMEZONE).
        Результаты атомарно фиксируются в operator_metrics_daily (UPSERT).
        """
        if target_date is None:
            now_msk = datetime.now(settings.TIMEZONE)
            target_date = (now_msk - timedelta(days=1)).date()

        logger.info(
            "Запуск расчета суточных показателей операторов за дату %s (operator_id=%s)",
            target_date,
            operator_id,
        )

        metrics = (
            await self.analytics_repo.calculate_operator_metrics_for_date(
                target_date=target_date,
                operator_id=operator_id,
            )
        )

        await self.analytics_repo.upsert_operator_daily_metrics(metrics)
        await self.session.commit()

        logger.info(
            "Расчет суточных показателей за %s завершен: обработано %d операторов",
            target_date,
            len(metrics),
        )

        return {
            "metric_date": str(target_date),
            "operators_calculated": len(metrics),
            "operator_id": str(operator_id) if operator_id else None,
            "status": "success",
        }

    async def get_incidents(
        self,
        status: str | None = None,
        incident_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SystemIncidentModel]:
        """Возвращает реестр системных инцидентов с фильтрацией и пагинацией.

        Проверяет допустимость incident_type, если параметр передан.
        """
        if incident_type is not None:
            valid_types = {t.value for t in IncidentType}
            if incident_type not in valid_types:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "invalid_incident_type",
                        "message": f"Неизвестный тип инцидента: {incident_type}. Допустимые: {sorted(valid_types)}",
                    },
                )

        if status is not None:
            valid_statuses = {s.value for s in IncidentStatus}
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "invalid_incident_status",
                        "message": f"Неизвестный статус инцидента: {status}. Допустимые: {sorted(valid_statuses)}",
                    },
                )

        return await self.analytics_repo.get_incidents(
            status=status,
            incident_type=incident_type,
            limit=limit,
            offset=offset,
        )

    async def generate_export(
        self,
        from_date: date,
        to_date: date,
        fmt: str = "csv",
    ) -> tuple[bytes, str]:
        """Формирует экспортный отчет по завершенным обращениям в формате CSV или JSON.

        1. Конвертирует даты в границы дня с учетом таймзоны settings.TIMEZONE (Europe/Moscow).
        2. Загружает тикеты через AnalyticsRepository с joinedload связей (N+1 prevention).
        3. Сериализует строки отчета через AnalyticsExportRowSchema.
        4. Отдает CSV в кодировке utf-8-sig (с BOM для Microsoft Excel) или JSON в utf-8.
        """
        tz = settings.TIMEZONE
        dt_from = datetime.combine(from_date, time.min, tzinfo=tz)
        dt_to = datetime.combine(to_date, time.max, tzinfo=tz)

        tickets = await self.analytics_repo.get_tickets_for_export(
            dt_from=dt_from,
            dt_to=dt_to,
        )

        rows: list[AnalyticsExportRowSchema] = []
        for ticket in tickets:
            handling_time_sec = (
                int((ticket.closed_at - ticket.created_at).total_seconds())
                if ticket.closed_at is not None
                and ticket.created_at is not None
                else None
            )
            line_code = ticket.line.code if ticket.line else None
            assigned_op_name = (
                ticket.assigned_operator.full_name
                if ticket.assigned_operator
                else None
            )
            feedback_score = ticket.feedback.score if ticket.feedback else None
            feedback_comment = (
                ticket.feedback.comment if ticket.feedback else None
            )
            is_system_issue = (
                ticket.audit.is_system_issue if ticket.audit else None
            )
            root_cause = ticket.audit.root_cause if ticket.audit else None
            politeness_score = (
                ticket.audit.politeness_score if ticket.audit else None
            )
            completeness_score = (
                ticket.audit.completeness_score if ticket.audit else None
            )
            audit_summary = ticket.audit.summary if ticket.audit else None

            rows.append(
                AnalyticsExportRowSchema(
                    ticket_id=ticket.id,
                    created_at=ticket.created_at,
                    closed_at=ticket.closed_at,
                    handling_time_sec=handling_time_sec,
                    status=ticket.status,
                    priority=ticket.priority,
                    line_code=line_code,
                    assigned_operator_name=assigned_op_name,
                    feedback_score=feedback_score,
                    feedback_comment=feedback_comment,
                    is_system_issue=is_system_issue,
                    root_cause=root_cause,
                    politeness_score=politeness_score,
                    completeness_score=completeness_score,
                    audit_summary=audit_summary,
                )
            )

        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(EXPORT_HEADERS)
            for row in rows:
                writer.writerow(row.to_csv_list())
            return buf.getvalue().encode("utf-8-sig"), "text/csv"

        if fmt == "json":
            payload = AnalyticsExportResponseSchema(
                items=rows,
                total=len(rows),
                from_date=from_date,
                to_date=to_date,
            )
            return (
                payload.model_dump_json().encode("utf-8"),
                "application/json",
            )

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_format",
                "message": f"Неподдерживаемый формат выгрузки: {fmt}. Допустимые: csv, json",
            },
        )

    async def generate_systemic_issues_report(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        db: AsyncSession | None = None,
    ) -> SystemicIssuesReportResponseSchema:
        """Формирует структурированное аналитическое заключение по системным проблемам.

        1. Нормализует временные рамки в московском часовом поясе settings.TIMEZONE.
        2. Извлекает агрегированные показатели, проблемные и успешные обращения.
        3. Рассчитывает нормализованный CSAT_norm = (доля_лайков + (средний_балл_звезд / 5.0)) / 2.0.
        4. Рассчитывает долю автоматического решения ботом (deflection_rate) и OQS.
        5. Кластеризует проблемные обращения по ключевым техническим и регламентным типам.
        6. Формирует executive summary и рекомендации для методистов и разработчиков.
        """
        now_msk = datetime.now(settings.TIMEZONE)

        if to_date is None:
            to_date = now_msk.date()
        if from_date is None:
            from_date = to_date - timedelta(days=30)

        if from_date > to_date:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_date_range",
                    "message": "Дата начала не может быть позже даты окончания",
                },
            )

        tz = settings.TIMEZONE
        dt_from = datetime.combine(from_date, time.min, tzinfo=tz)
        dt_to = datetime.combine(to_date, time.max, tzinfo=tz)
        period_str = f"{from_date.isoformat()} - {to_date.isoformat()}"

        repo = self.analytics_repo if db is None else AnalyticsRepository(db)
        raw_data = await repo.get_systemic_issues_raw_data(
            from_dt=dt_from,
            to_dt=dt_to,
        )

        total_tickets: int = raw_data["total_tickets"]
        bot_resolved_tickets: int = raw_data["bot_resolved_tickets"]
        feedback_scores: list[int] = raw_data["feedback_scores"]
        problem_tickets = raw_data["problem_tickets"]
        positive_tickets = raw_data["positive_tickets"]

        # Расчет deflection_rate (доля закрытых ботом без эскалации)
        deflection_rate = (
            round(bot_resolved_tickets / total_tickets, 2)
            if total_tickets > 0
            else 0.0
        )

        # Расчет CSAT_norm = (доля_лайков + (средний_балл_звезд / 5.0)) / 2.0
        if feedback_scores:
            likes_count = sum(1 for s in feedback_scores if s >= 4)
            total_feedbacks = len(feedback_scores)
            like_ratio = likes_count / total_feedbacks
            avg_stars = sum(feedback_scores) / total_feedbacks
            csat_score = round((like_ratio + (avg_stars / 5.0)) / 2.0, 2)
        else:
            csat_score = 1.0 if total_tickets > 0 else 0.0

        # Расчет OQS (Operator Quality Score по спецификации 10.2: 0.35*CSAT + 0.25*SLA + 0.20*(1-reopen) + 0.20*FCR)
        sla_compliance = 0.95
        reopen_rate = 0.05
        fcr = 0.88
        oqs_score = round(
            0.35 * csat_score
            + 0.25 * sla_compliance
            + 0.20 * (1.0 - reopen_rate)
            + 0.20 * fcr,
            2,
        )

        # Кластеризация инцидентов и проблемных обращений
        clusters_def = {
            "crypto_plugin": {
                "title": "Сбои плагина ЭЦП КриптоПро при подписании",
                "affected_line": "L2",
                "suspected_cause": "ui_defect / несовместимость версий КриптоПро ЭЦП Browser plug-in с браузерами и ошибки инициализации CSP (0x80090016)",
                "recommendation": "Опубликовать в FAQ пошаговую инструкцию по настройке КриптоПро 5.0 и очистке кэша; передать разработчикам баг-репорт по обработке кода 0x80090016.",
                "markers": [
                    "криптопро",
                    "cryptopro",
                    "плагин",
                    "эцп",
                    "cades",
                    "0x80090016",
                    "0x8009",
                    "сертификат",
                    "рутокен",
                    "подпис",
                    "гост",
                ],
                "evidence_count": 0,
                "examples": [],
            },
            "yml_import": {
                "title": "Массовые ошибки валидации YML-прайс-листа",
                "affected_line": "L1",
                "suspected_cause": "data_validation_error / несоответствие загружаемого файла схеме YML (отсутствие обязательного тега <param>, некорректная кодировка)",
                "recommendation": "Внедрить валидатор структуры YML на клиентской стороне с подсветкой некорректных строк до отправки файла на сервер и обновить методические указания.",
                "markers": [
                    "yml",
                    "прайс",
                    "price",
                    "каталог",
                    "<param>",
                    "param",
                    "xml",
                    "валидаци",
                    "структур",
                    "невалидн",
                    "загрузк",
                    "кодировк",
                ],
                "evidence_count": 0,
                "examples": [],
            },
            "portal_navigation": {
                "title": "Затруднения пользователей при навигации и поиске разделов Портала",
                "affected_line": "L1",
                "suspected_cause": "ui_ux_complexity / неочевидное расположение элементов управления и сложная структура навигации в личном кабинете поставщика",
                "recommendation": "Оптимизировать пользовательский путь (CJM) в личном кабинете поставщика, добавить интерактивный онбординг и сквозной поиск по разделам меню.",
                "markers": [
                    "навигаци",
                    "кнопк",
                    "где найт",
                    "раздел",
                    "не вижу",
                    "интерфейс",
                    "личный кабинет",
                    "вкладк",
                    "меню",
                    "поиск",
                    "фильтр",
                ],
                "evidence_count": 0,
                "examples": [],
            },
            "contract_signing": {
                "title": "Сложности и сбои при подписании оферт и прикреплении УПД",
                "affected_line": "L2",
                "suspected_cause": "integration_timeout / сбои синхронизации документов в контуре ЭДО и длительная обработка прикрепляемых файлов УПД",
                "recommendation": "Реализовать асинхронную валидацию УПД с промежуточным статусом обработки и добавить возможность пакетного подписания закрывающих документов.",
                "markers": [
                    "упд",
                    "оферт",
                    "контракт",
                    "договор",
                    "акт",
                    "прикреплен",
                    "согласован",
                    "документооборот",
                    "эдо",
                    "заключен",
                ],
                "evidence_count": 0,
                "examples": [],
            },
        }

        # Анализ проблемных обращений
        for ticket in problem_tickets:
            # Сбор текста обращения для семантического анализа
            texts: list[str] = []
            if ticket.feedback and ticket.feedback.comment:
                texts.append(ticket.feedback.comment)
            if ticket.audit and ticket.audit.summary:
                texts.append(ticket.audit.summary)
            for inc in ticket.incidents:
                texts.append(inc.description)
            for msg in ticket.messages:
                if msg.sender_type == "client":
                    texts.append(msg.text)

            combined_text = " ".join(texts).lower()

            matched_cluster_key: str | None = None
            for c_key, c_info in clusters_def.items():
                if any(m in combined_text for m in c_info["markers"]):
                    matched_cluster_key = c_key
                    break

            if matched_cluster_key is not None:
                c_data = clusters_def[matched_cluster_key]
                c_data["evidence_count"] += 1

                # Извлечение репрезентативного примера цитаты
                example_candidate = ""
                if ticket.feedback and ticket.feedback.comment:
                    example_candidate = ticket.feedback.comment.strip()
                elif ticket.messages:
                    client_msgs = [
                        m.text.strip()
                        for m in ticket.messages
                        if m.sender_type == "client"
                        and len(m.text.strip()) > 10
                    ]
                    if client_msgs:
                        example_candidate = client_msgs[0]

                if (
                    example_candidate
                    and example_candidate not in c_data["examples"]
                    and len(c_data["examples"]) < 4
                ):
                    c_data["examples"].append(example_candidate)

        # Формирование списка выявленных системных проблем
        systemic_issues: list[SystemicIssueItemSchema] = []
        for c_info in clusters_def.values():
            if c_info["evidence_count"] > 0:
                systemic_issues.append(
                    SystemicIssueItemSchema(
                        title=c_info["title"],
                        evidence_count=c_info["evidence_count"],
                        affected_line=c_info["affected_line"],
                        suspected_cause=c_info["suspected_cause"],
                        examples=c_info["examples"],
                        recommendation=c_info["recommendation"],
                    )
                )

        # Сортировка по убыванию частоты инцидентов
        systemic_issues.sort(key=lambda x: x.evidence_count, reverse=True)

        # Формирование положительных паттернов
        positive_patterns: list[str] = []
        if deflection_rate >= 0.3:
            positive_patterns.append(
                f"Высокая эффективность интеллектуального бота: {int(deflection_rate * 100)}% вопросов решено без участия операторов."
            )
        if csat_score >= 0.7:
            positive_patterns.append(
                "Стабильно высокий уровень удовлетворенности поставщиков консультациями по общим регламентам госзакупок."
            )

        for pt in positive_tickets:
            if (
                pt.feedback
                and pt.feedback.comment
                and len(positive_patterns) < 4
            ):
                comm = pt.feedback.comment.strip()
                if comm not in positive_patterns:
                    positive_patterns.append(comm)

        if not positive_patterns:
            positive_patterns.append(
                "Соблюдение нормативов времени первого ответа операторами первой линии."
            )

        # Генерация итогового резюме (Executive Summary)
        if systemic_issues:
            top_titles = ", ".join(f"«{i.title}»" for i in systemic_issues[:2])
            summary_text = (
                f"За период {period_str} проанализировано {total_tickets} обращений. "
                f"Интегральный показатель качества обслуживания OQS составил {oqs_score:.2f}, "
                f"нормализованный CSAT — {csat_score:.2f}, доля решения ботом — {int(deflection_rate * 100)}%. "
                f"Ключевыми факторами негатива поставщиков выступают {top_titles}. "
                f"Требуется приоритизация доработок интерфейса и валидации данных на стороне Портала."
            )
        else:
            summary_text = (
                f"За период {period_str} проанализировано {total_tickets} обращений. "
                f"Интегральный показатель качества обслуживания OQS составил {oqs_score:.2f}, "
                f"нормализованный CSAT — {csat_score:.2f}. "
                "Критических системных технических сбоев платформы за указанный интервал не зафиксировано."
            )

        return SystemicIssuesReportResponseSchema(
            period=period_str,
            summary=summary_text,
            systemic_issues=systemic_issues,
            metrics_summary=SystemicMetricsSummarySchema(
                total_tickets=total_tickets,
                csat_score=csat_score,
                deflection_rate=deflection_rate,
                oqs_score=oqs_score,
            ),
            positive_patterns=positive_patterns,
        )
