"""Юнит-тесты связки Copilot с локальной LLM и бесшовного отката при таймауте (Подплан 3)."""

from unittest.mock import AsyncMock

import pytest
import uuid6

from src.rag.copilot import (
    CopilotService,
    OllamaCopilotLlmClient,
)
from src.rag.schemas import CopilotLlmOutputSchema


@pytest.mark.asyncio
async def test_ollama_copilot_client_success() -> None:
    """Проверяет успешное получение и парсинг ответа от Ollama."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "summary": "Сбой входа по ЭЦП",
        "suggested_line_code": "L2",
        "suggested_response": "Проверьте плагин",
        "recommended_chunk_ids": ["c1"],
    }

    client = OllamaCopilotLlmClient(llm_client=mock_llm, timeout=4.0)
    res = await client.generate_copilot_summary(
        prompt="Не могу войти с сертификатом",
        system_prompt="sys",
        timeout=4.0,
    )

    assert isinstance(res, CopilotLlmOutputSchema)
    assert res.summary == "Сбой входа по ЭЦП"
    assert res.suggested_line_code == "L2"
    assert res.suggested_response == "Проверьте плагин"


@pytest.mark.asyncio
async def test_ollama_copilot_client_timeout_fallback() -> None:
    """Проверяет бесшовный откат на быстрый шаблон при таймауте локальной модели."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.side_effect = TimeoutError("Ollama timeout")

    client = OllamaCopilotLlmClient(llm_client=mock_llm, timeout=4.0)
    res = await client.generate_copilot_summary(
        prompt="Ошибка 0x80090016 при подписании",
        system_prompt="sys",
        timeout=4.0,
    )

    # Проверяем, что вернулся валидный результат без исключения
    assert isinstance(res, CopilotLlmOutputSchema)
    assert res.suggested_line_code == "L2"
    assert "КриптоПро" in res.suggested_response


@pytest.mark.asyncio
async def test_copilot_service_default_fallback_without_crash() -> None:
    """Проверяет отказоустойчивость сервиса при сбое инференса."""
    failing_client = AsyncMock()
    failing_client.generate_copilot_summary.side_effect = RuntimeError(
        "Host unreachable"
    )

    service = CopilotService(llm_client=failing_client, timeout=4.0)
    summary = await service.build_copilot_summary(
        ticket_id=uuid6.uuid7(),
        messages=[
            {"sender": "client", "text": "Как отправить протокол разногласий?"}
        ],
    )

    assert summary.suggested_line_code == "L1"
    assert "протокол разногласий" in summary.summary.lower()
