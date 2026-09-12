"""Генерация сводки диалога и подсказок оператору (Copilot)."""

import asyncio
import json
import logging
from typing import Any, ClassVar, Protocol, runtime_checkable
from uuid import UUID

import httpx
from qdrant_client import AsyncQdrantClient

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.operators.schemas import (
    CopilotSummaryResponseSchema,
    SimilarTicketItemSchema,
)
from src.rag.qdrant_tickets import search_similar_resolved_tickets
from src.rag.schemas import CopilotLlmOutputSchema

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_PROMPT = (
    "Ты — экспертный аналитический ассистент AI Copilot для операторов службы поддержки "
    "Портала поставщиков Москвы (ЕАИСТ) и госзакупок по 44-ФЗ и 223-ФЗ.\n\n"
    "Твоя задача — проанализировать историю диалога клиента и подготовить:\n"
    "1. summary: краткую суть проблемы (1-2 предложения, строго факты без лишних слов);\n"
    "2. suggested_line_code: рекомендованную линию поддержки (L1 - регламенты и навигация, "
    "L2 - ошибки ЭЦП, КриптоПро и технические сбои, L3 - претензии, ФАС, блокировки и споры);\n"
    "3. suggested_response: вежливый, профессиональный готовый черновик ответа для оператора "
    "с четкими инструкциями по шагам;\n"
    "4. recommended_chunk_ids: идентификаторы нормативных статей из базы знаний.\n\n"
    "Ответ должен быть строго валидным объектом CopilotLlmOutputSchema."
)


@runtime_checkable
class CopilotLlmClientProtocol(Protocol):
    """Протокол вызова языковой модели для генерации сводки Copilot."""

    async def generate_copilot_summary(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float = 30.0,
    ) -> CopilotLlmOutputSchema:
        """Генерирует структурированную аналитическую выжимку и черновик решения."""
        ...


class MockCopilotLlmClient:
    """Детерминированный тестовый клиент генерации подсказок Copilot."""

    TECH_MARKERS: ClassVar[set[str]] = {
        "0x",
        "криптопро",
        "эцп",
        "cades",
        "рутокен",
        "плагин",
        "сертификат",
        "cadesplugin",
        "csp",
    }

    DISPUTE_MARKERS: ClassVar[set[str]] = {
        "фас",
        "суд",
        "судебн",
        "исков",
        "жалоб",
        "претензи",
        "расторг",
        "блокировк",
        "рнп",
        "уклон",
    }

    def __init__(
        self,
        default_output: CopilotLlmOutputSchema | None = None,
        delay: float = 0.0,
        fail_times: int = 0,
    ) -> None:
        """Инициализирует тестовый генератор подсказок."""
        self.default_output = default_output
        self.delay = delay
        self.fail_times = fail_times
        self.call_count = 0

    async def generate_copilot_summary(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float = 30.0,
    ) -> CopilotLlmOutputSchema:
        """Эмулирует структурированный ответ языковой модели с контекстной эвристикой."""
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.call_count <= self.fail_times:
            raise TimeoutError("LLM copilot generation timeout (mock failure)")

        if self.default_output is not None:
            return self.default_output.model_copy(deep=True)

        lowered = prompt.lower()

        # 1. Проверка технических маркеров ЭЦП и плагинов -> Линия L2
        if any(marker in lowered for marker in self.TECH_MARKERS):
            return CopilotLlmOutputSchema(
                summary=(
                    "Пользователь столкнулся со сбоем плагина ЭЦП / КриптоПро CSP при попытке "
                    "подписания документа на Портале поставщиков."
                ),
                suggested_line_code="L2",
                suggested_response=(
                    "Здравствуйте! По вашей проблеме с электронной подписью рекомендуем: "
                    "1) Проверить видимость личного сертификата в панели КриптоПро CSP; "
                    "2) Переустановить КриптоПро ЭЦП Browser plug-in; "
                    "3) Добавить сайт https://zakupki.mos.ru в список доверенных узлов браузера."
                ),
                recommended_chunk_ids=[
                    "chunk_portal_zakupki_reglament_sec4_p1"
                ],
            )

        # 2. Проверка маркеров споров, ФАС и блокировок -> Линия L3
        if any(marker in lowered for marker in self.DISPUTE_MARKERS):
            return CopilotLlmOutputSchema(
                summary=(
                    "Обращение связано с претензионной работой, угрозой жалобы в ФАС "
                    "или блокировкой учетной записи поставщика."
                ),
                suggested_line_code="L3",
                suggested_response=(
                    "Здравствуйте! Ваше обращение принято в работу старшим специалистом. "
                    "Рекомендуем зафиксировать скриншоты системного времени и направить официальное "
                    "уведомление заказчику о возникших технических обстоятельствах."
                ),
                recommended_chunk_ids=[],
            )

        # 3. Регламентные вопросы (котировочные сессии, протоколы разногласий) -> Линия L1
        return CopilotLlmOutputSchema(
            summary=(
                "Вопрос клиента: регламентные сроки, протокол разногласий "
                "по котировочной сессии на Портале поставщиков."
            ),
            suggested_line_code="L1",
            suggested_response=(
                "Добрый день! В соответствии с разделом 4 Регламента Портала поставщиков Москвы, "
                "вы вправе сформировать и направить протокол разногласий в личном кабинете "
                "в течение 3 рабочих дней с момента размещения проекта контракта заказчиком."
            ),
            recommended_chunk_ids=["chunk_portal_zakupki_reglament_sec4_p1"],
        )


class OllamaCopilotLlmClient:
    """Клиент вызова локального инференса Ollama (/v1/chat/completions) с таймаутом и фолбэком."""

    DEFAULT_TIMEOUT: float = 4.0

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 4.0,
    ) -> None:
        """Инициализирует подключение к локальному сервису Ollama."""
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout
        self.fallback_client = MockCopilotLlmClient()

    async def generate_copilot_summary(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float | None = None,
    ) -> CopilotLlmOutputSchema:
        """Запрашивает подсказку у Ollama с ограничением времени до 4.0с и бесшовным откатом."""
        effective_timeout = timeout if timeout is not None else self.timeout
        endpoint = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        timeout_config = httpx.Timeout(
            effective_timeout, connect=min(1.5, effective_timeout)
        )

        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(endpoint, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    cleaned_content = content.strip()
                    cleaned_content = cleaned_content.removeprefix("```json")
                    cleaned_content = cleaned_content.removeprefix("```")
                    cleaned_content = cleaned_content.removesuffix("```")
                    cleaned_content = cleaned_content.strip()

                    parsed = json.loads(cleaned_content)
                    return CopilotLlmOutputSchema.model_validate(parsed)

                logger.warning(
                    "Ollama API returned status %s. Triggering fallback.",
                    response.status_code,
                )
        except (httpx.TimeoutException, TimeoutError) as exc:
            logger.warning(
                "Ollama copilot timeout (%.1fs): %s. Seamless fallback to template.",
                effective_timeout,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Ollama copilot inference error: %s. Seamless fallback to template.",
                exc,
            )

        # Бесшовный откат на быстрый эвристический ответ без падения интерфейса
        return await self.fallback_client.generate_copilot_summary(
            prompt=prompt,
            system_prompt=system_prompt,
            timeout=effective_timeout,
        )


class CopilotService:
    """Сервис формирования аналитической подсказки оператора и подбора прецедентов."""

    DEFAULT_TIMEOUT: float = 4.0

    def __init__(
        self,
        llm_client: CopilotLlmClientProtocol | None = None,
        qdrant_client: AsyncQdrantClient | None = None,
        timeout: float = 4.0,
    ) -> None:
        """Инициализирует сервис клиентом LLM и клиентом Qdrant."""
        self.timeout = timeout
        self.fallback_client = MockCopilotLlmClient()
        self.llm_client = llm_client or OllamaCopilotLlmClient(timeout=timeout)
        self.qdrant_client = qdrant_client

    def _format_conversation(self, messages: list[dict[str, Any]]) -> str:
        """Форматирует переписку в компактный диалоговый контекст для промпта."""
        lines: list[str] = []
        for msg in messages:
            sender = str(
                msg.get("sender") or msg.get("sender_type") or "client"
            )
            text = str(msg.get("text") or "").strip()
            if text:
                lines.append(f"{sender}: {text}")

        return "\n".join(lines) if lines else "История диалога пуста."

    def _extract_last_user_query(self, messages: list[dict[str, Any]]) -> str:
        """Извлекает последнюю реплику клиента для семантического поиска в базе прецедентов."""
        for msg in reversed(messages):
            sender = str(msg.get("sender") or msg.get("sender_type") or "")
            if sender in ("client", "user"):
                text = str(msg.get("text") or "").strip()
                if text:
                    return text

        # Фолбэк: если реплик клиента не найдено, берем последнее непустое сообщение
        for msg in reversed(messages):
            text = str(msg.get("text") or "").strip()
            if text:
                return text

        return ""

    async def build_copilot_summary(
        self,
        ticket_id: UUID | str,
        messages: list[dict[str, Any]],
        qdrant_client: AsyncQdrantClient | None = None,
    ) -> CopilotSummaryResponseSchema:
        """Формирует выжимку диалога, черновик ответа и находит похожие прецеденты в Qdrant."""
        target_qdrant = (
            qdrant_client or self.qdrant_client or get_qdrant_client()
        )
        conversation_context = self._format_conversation(messages)
        user_query = self._extract_last_user_query(messages)

        # 1. Поиск похожих закрытых кейсов в Qdrant
        similar_tickets: list[SimilarTicketItemSchema] = []
        if target_qdrant is not None and user_query:
            similar_tickets = await search_similar_resolved_tickets(
                client=target_qdrant,
                query_text=user_query,
                limit=3,
            )

        # 2. Генерация аналитической выжимки через LLM с таймаутом до 4.0с
        prompt = (
            f"ИСТОРИЯ ОБРАЩЕНИЯ (ТИКЕТ {ticket_id}):\n"
            f"{conversation_context}\n\n"
            "Сформируй краткую суть, выбери линию поддержки и составь черновик ответа."
        )

        try:
            llm_output = await asyncio.wait_for(
                self.llm_client.generate_copilot_summary(
                    prompt=prompt,
                    system_prompt=COPILOT_SYSTEM_PROMPT,
                    timeout=self.timeout,
                ),
                timeout=self.timeout,
            )
        except Exception as exc:
            logger.warning(
                "Copilot LLM execution error/timeout: %s. Using heuristic fallback.",
                exc,
            )
            llm_output = await self.fallback_client.generate_copilot_summary(
                prompt=prompt,
                system_prompt=COPILOT_SYSTEM_PROMPT,
                timeout=self.timeout,
            )

        # 3. Агрегация в публичную контрактную схему
        return CopilotSummaryResponseSchema(
            summary=llm_output.summary,
            suggested_line_code=llm_output.suggested_line_code,
            suggested_response=llm_output.suggested_response,
            recommended_chunk_ids=llm_output.recommended_chunk_ids,
            similar_resolved_tickets=similar_tickets,
        )
