"""Юнит-тесты связки Copilot с локальной LLM и бесшовного отката при таймауте (Подплан 3)."""

from unittest.mock import AsyncMock, patch

import pytest
import uuid6

from src.rag.copilot import (
    CopilotService,
    OllamaCopilotLlmClient,
)
from src.rag.schemas import CopilotLlmOutputSchema


@pytest.mark.asyncio
async def test_ollama_copilot_client_success() -> None:
    """Проверяет успешное получение и парсинг ответа от Ollama /v1/chat/completions."""
    client = OllamaCopilotLlmClient(
        base_url="http://localhost:11434",
        model="qwen3.5:2b-instruct",
        timeout=4.0,
    )

    from unittest.mock import MagicMock

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"summary": "Сбой входа по ЭЦП", "suggested_line_code": "L2", "suggested_response": "Проверьте плагин", "recommended_chunk_ids": ["c1"]}'
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
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
    client = OllamaCopilotLlmClient(timeout=4.0)

    # Симулируем таймаут сетевого вызова
    with patch(
        "httpx.AsyncClient.post", side_effect=TimeoutError("Ollama timeout")
    ):
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
