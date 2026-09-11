"""Модуль оценки качества диалогов языковой моделью (LLM-Judge)."""

import asyncio
import logging
from typing import Any, ClassVar, Protocol, runtime_checkable

from src.analytics.models import IncidentType, RootCauseType
from src.analytics.schemas import AuditLlmOutputSchema

logger = logging.getLogger(__name__)

AUDIT_SYSTEM_PROMPT = (
    "Ты — беспристрастный экспертный арбитр и аудитор качества диалогов службы поддержки "
    "Портала поставщиков Москвы (ЕАИСТ) и госзакупок по 44-ФЗ и 223-ФЗ.\n\n"
    "Твоя задача — объективно оценить завершенный диалог между клиентом и поддержкой:\n"
    "1. politeness_score (1-5): вежливость, культура речи, корректность тона;\n"
    "2. completeness_score (1-5): полнота, точность консультации и следование регламентам;\n"
    "3. root_cause: первопричина проблемы или негатива:\n"
    "   - 'operator_error': некомпетентность, грубость, неверные инструкции или игнорирование;\n"
    "   - 'system_issue': технический сбой портала, плагина ЭЦП, КриптоПро, СМЭВ, ошибка 0x, недоступность страниц;\n"
    "   - 'regulation_dissatisfaction': несогласие клиента с 44-ФЗ/223-ФЗ, отклонением заявки или сроками при корректном ответе оператора;\n"
    "   - 'none': обращение решено корректно, претензий нет.\n"
    "4. summary: краткое (1-3 предложения) аргументированное заключение аудита;\n"
    "5. is_system_issue: true, если выявлен сбой платформы (для снятия вины с сотрудника);\n"
    "6. incident_type: 'portal_downtime', 'crypto_plugin' или 'api_error' при наличии системного сбоя.\n\n"
    "Ответ должен быть строго валидным объектом AuditLlmOutputSchema."
)


@runtime_checkable
class AuditLlmClientProtocol(Protocol):
    """Протокол вызова языковой модели для аудита диалога."""

    async def evaluate_dialog(
        self,
        prompt: str,
        system_prompt: str = AUDIT_SYSTEM_PROMPT,
        timeout: float = 30.0,
    ) -> AuditLlmOutputSchema:
        """Оценивает диалог и возвращает структурированный вердикт."""
        ...


def build_audit_dialog_context(
    ticket_id: Any,
    line_code: str | None,
    assigned_operator_name: str | None,
    feedback_score: int | None,
    feedback_comment: str | None,
    messages: list[dict[str, Any]],
) -> str:
    """Формирует структурированный контекст диалога для подачи в LLM-Judge."""
    lines: list[str] = [
        "=== МЕТАДАННЫЕ ОБРАЩЕНИЯ ===",
        f"ID тикета: {ticket_id}",
        f"Линия поддержки: {line_code or 'Не определена'}",
        f"Оператор: {assigned_operator_name or 'Без оператора (только бот)'}",
    ]

    if feedback_score is not None:
        lines.append(
            f"Отзыв клиента: Оценка {feedback_score}/5, Комментарий: {feedback_comment or 'Без комментария'}"
        )
    else:
        lines.append("Отзыв клиента: Не оставлен (аудит по таймауту)")

    lines.append("\n=== СТЕНОГРАММА ДИАЛОГА ===")
    for msg in messages:
        sender_type = msg.get("sender", "").lower()
        text = msg.get("text", "").strip()

        if sender_type == "client":
            role_tag = "[КЛИЕНТ]"
        elif sender_type == "operator":
            role_tag = "[ОПЕРАТОР]"
        elif sender_type == "bot":
            role_tag = "[БОТ]"
        else:
            role_tag = "[СИСТЕМА]"

        lines.append(f"{role_tag}: {text}")

    return "\n".join(lines)


class MockAuditLlmClient:
    """Детерминированный тестовый оценщик диалогов с распознаванием маркеров."""

    TECH_MARKERS: ClassVar[set[str]] = {
        "0x",
        "криптопро",
        "cades",
        "эцп",
        "рутокен",
        "плагин",
        "сертификат",
        "сбой",
        "недоступен",
        "висит",
        "падает",
        "портал",
        "502",
        "504",
        "ошибка подписи",
    }

    REGULATION_MARKERS: ClassVar[set[str]] = {
        "44-фз",
        "223-фз",
        "закон",
        "регламент",
        "отклонили",
        "срок",
        "комиссия",
        "фас",
        "госзакуп",
        "реестр",
    }

    OPERATOR_ERROR_MARKERS: ClassVar[set[str]] = {
        "груб",
        "хам",
        "не помог",
        "тупой",
        "идиот",
        "ужас",
        "отвратительн",
        "бросил",
        "некомпетентен",
        "не знает",
    }

    def __init__(
        self,
        default_output: AuditLlmOutputSchema | None = None,
        delay: float = 0.0,
        fail_times: int = 0,
    ) -> None:
        """Инициализирует тестовый LLM-оценщик."""
        self.default_output = default_output
        self.delay = delay
        self.fail_times = fail_times
        self.call_count = 0

    async def evaluate_dialog(
        self,
        prompt: str,
        system_prompt: str = AUDIT_SYSTEM_PROMPT,
        timeout: float = 30.0,
    ) -> AuditLlmOutputSchema:
        """Эмулирует структурированный ответ языковой модели на основе анализа контекста."""
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.call_count <= self.fail_times:
            raise TimeoutError("LLM audit generation timeout (mock failure)")

        if self.default_output is not None:
            return self.default_output.model_copy()

        text_lower = prompt.lower()

        # 1. Положительный отзыв (4-5 звезд)
        if "оценка 4/5" in text_lower or "оценка 5/5" in text_lower:
            return AuditLlmOutputSchema(
                politeness_score=5,
                completeness_score=5,
                root_cause=RootCauseType.NONE,
                summary="Диалог проведен профессионально, клиент полностью удовлетворен предоставленной помощью.",
                is_system_issue=False,
                incident_type=None,
                incident_description=None,
            )

        # 2. Выявление технического сбоя платформы/плагина
        has_tech_issue = any(m in text_lower for m in self.TECH_MARKERS)
        if has_tech_issue:
            incident_type = (
                IncidentType.CRYPTO_PLUGIN
                if any(
                    k in text_lower
                    for k in ["крипто", "эцп", "плагин", "cades", "0x"]
                )
                else IncidentType.PORTAL_DOWNTIME
            )
            return AuditLlmOutputSchema(
                politeness_score=4,
                completeness_score=4,
                root_cause=RootCauseType.SYSTEM_ISSUE,
                summary="Выявлен технический сбой на стороне инфраструктуры платформы или средств электронной подписи.",
                is_system_issue=True,
                incident_type=incident_type,
                incident_description=f"Технический сбой ({incident_type}): ошибка подписания или недоступность сервиса на шаге работы клиента.",
            )

        # 3. Выявление несогласия с нормами законодательства
        has_reg_issue = any(m in text_lower for m in self.REGULATION_MARKERS)
        if has_reg_issue:
            return AuditLlmOutputSchema(
                politeness_score=4,
                completeness_score=4,
                root_cause=RootCauseType.REGULATION_DISSATISFACTION,
                summary="Недовольство клиента обусловлено требованиями законодательства (44-ФЗ/223-ФЗ); оператор проконсультировал корректно.",
                is_system_issue=False,
                incident_type=None,
                incident_description=None,
            )

        # 4. Выявление ошибки или некорректного поведения оператора
        has_op_error = any(
            m in text_lower for m in self.OPERATOR_ERROR_MARKERS
        )
        if (
            has_op_error
            or "оценка 1/5" in text_lower
            or "оценка 2/5" in text_lower
        ):
            return AuditLlmOutputSchema(
                politeness_score=2,
                completeness_score=2,
                root_cause=RootCauseType.OPERATOR_ERROR,
                summary="Зафиксированы нарушения стандартов обслуживания: неполное решение проблемы или некорректный тон сотрудника.",
                is_system_issue=False,
                incident_type=None,
                incident_description=None,
            )

        # 5. Дефолтный нейтральный аудит
        return AuditLlmOutputSchema(
            politeness_score=4,
            completeness_score=4,
            root_cause=RootCauseType.NONE,
            summary="Диалог соответствует базовым требованиям регламента поддержки.",
            is_system_issue=False,
            incident_type=None,
            incident_description=None,
        )
