"""Интеллектуальный классификатор линий поддержки (L1/L2) при эскалации диалога."""

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.llm_client import get_llm_stream_client

logger = logging.getLogger(__name__)

ESCALATION_ROUTER_SYSTEM_PROMPT = (
    "Распредели обращение на Портале поставщиков между линиями L1 и L2.\n"
    "L1 (колл-центр): простые вопросы, регистрация, назначение портала, общая навигация, фиксация проблем.\n"
    "L2 (эксперты): работа в системе, заполнение контракта/оферты, законы (44-ФЗ, 223-ФЗ), сценарии по базе знаний, сбои.\n"
    "На L3 не направлять.\n"
    'Верни только JSON: {"line": "L1"|"L2", "reason": "краткая причина"}'
)


class EscalationRouteOutput(BaseModel):
    """Результат классификации линии поддержки при эскалации тикета."""

    line: Literal["L1", "L2"] = Field(
        ...,
        description="Назначенная линия поддержки: L1 (колл-центр) или L2 (экспертная)",
    )
    reason: str = Field(
        ...,
        description="Краткое обоснование выбора линии",
    )


def build_escalation_prompt(
    conversation_history: list[dict[str, Any]],
    client_reason: str | None = None,
) -> str:
    """Формирует компактный контекст переписки и причины вызова оператора."""
    lines: list[str] = []
    if conversation_history:
        recent = conversation_history[-6:]
        for item in recent:
            sender = str(
                item.get("sender")
                or item.get("sender_type")
                or item.get("role")
                or "user"
            )
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(f"[{sender}]: {text}")

    dialogue = "\n".join(lines) if lines else "История диалога пуста."
    reason_line = (
        f"Причина вызова: {client_reason.strip()}"
        if client_reason and client_reason.strip()
        else ""
    )

    parts = [
        p
        for p in [reason_line, f"Диалог:\n{dialogue}", "Выбери L1 или L2."]
        if p
    ]
    return "\n\n".join(parts)


class EscalationRouter:
    """Сервис классификации обращений по линиям поддержки (L1/L2) при эскалации."""

    def __init__(
        self,
        llm_client: Any | None = None,
        timeout: float = 15.0,
    ) -> None:
        """Инициализирует маршрутизатор клиентом LLM и таймаутом."""
        self.llm_client = llm_client or get_llm_stream_client()
        self.timeout = timeout

    @staticmethod
    def _normalize_line(value: Any) -> Literal["L1", "L2"]:
        """Нормализует строковый ответ модели к L1 или L2."""
        val_str = str(value or "").strip().upper()
        if val_str in ("L1", "L2"):
            return val_str  # type: ignore[return-value]
        if "2" in val_str or "ТЕХ" in val_str:
            return "L2"
        return "L1"

    async def route(
        self,
        conversation_history: list[dict[str, Any]],
        client_reason: str | None = None,
    ) -> EscalationRouteOutput:
        """Определяет линию поддержки через LLM с надежным фолбэком на L1."""
        prompt = build_escalation_prompt(
            conversation_history=conversation_history,
            client_reason=client_reason,
        )

        try:
            raw_dict = await self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=ESCALATION_ROUTER_SYSTEM_PROMPT,
                timeout=self.timeout,
            )

            line = self._normalize_line(raw_dict.get("line"))
            reason = str(
                raw_dict.get("reason")
                or f"Назначена линия {line} по результатам анализа обращения"
            ).strip()

            return EscalationRouteOutput(line=line, reason=reason)

        except Exception as exc:
            logger.warning(
                "Сбой классификации линии эскалации через LLM (%s). Активирован страховочный фолбэк на L1",
                exc,
            )
            return EscalationRouteOutput(
                line="L1",
                reason="Автоматический фолбэк на первую линию (таймаут или сбой модели)",
            )
