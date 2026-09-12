"""Тесты боевых клиентов OllamaAuditLlmClient и OllamaCopilotLlmClient."""

from unittest.mock import AsyncMock

import pytest

from src.analytics.evaluator import MockAuditLlmClient, OllamaAuditLlmClient
from src.analytics.models import IncidentType, RootCauseType
from src.rag.copilot import MockCopilotLlmClient, OllamaCopilotLlmClient


@pytest.mark.asyncio
async def test_ollama_audit_llm_client_success():
    """Проверяет успешный разбор валидного JSON ответа Ollama."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "politeness_score": 5,
        "completeness_score": 4,
        "root_cause": "none",
        "summary": "Оператор проконсультировал вежливо и по существу.",
        "is_system_issue": False,
        "incident_type": None,
        "incident_description": None,
    }

    client = OllamaAuditLlmClient(llm_client=mock_llm)
    result = await client.evaluate_dialog(prompt="Контекст обращения...")

    assert result.politeness_score == 5
    assert result.completeness_score == 4
    assert result.root_cause == RootCauseType.NONE
    assert result.is_system_issue is False
    assert "вежливо" in result.summary


@pytest.mark.asyncio
async def test_ollama_audit_llm_client_normalization():
    """Проверяет нормализацию некорректных значений от компактной модели."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "politeness_score": 10,  # Выше 5
        "completeness_score": -2,  # Ниже 1
        "root_cause": "unexpected_string_cause",
        "summary": "",
        "is_system_issue": True,
        "incident_type": "crypto_plugin",
    }

    client = OllamaAuditLlmClient(llm_client=mock_llm)
    result = await client.evaluate_dialog(prompt="Контекст обращения...")

    # Оценки должны быть ограничены диапазоном 1..5
    assert result.politeness_score == 5
    assert result.completeness_score == 1
    # Неизвестный root_cause сбрасывается в NONE
    assert result.root_cause == RootCauseType.NONE
    assert result.is_system_issue is True
    assert result.incident_type == IncidentType.CRYPTO_PLUGIN
    assert len(result.summary) > 0


@pytest.mark.asyncio
async def test_ollama_audit_llm_client_fallback_on_network_error():
    """Проверяет автоматический переход на MockAuditLlmClient при сбое соединения."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.side_effect = ConnectionError(
        "Ollama server unreachable"
    )

    fallback = MockAuditLlmClient()
    client = OllamaAuditLlmClient(
        llm_client=mock_llm, fallback_client=fallback
    )

    # В промпте передаем маркер сбоя ЭЦП
    prompt = "Пользователь пишет: ошибка плагина КриптоПро 0x80090016"
    result = await client.evaluate_dialog(prompt=prompt)

    # Заглушка должна перехватить маркер и зафиксировать системный сбой
    assert result.is_system_issue is True
    assert result.root_cause == RootCauseType.SYSTEM_ISSUE
    assert result.incident_type == IncidentType.CRYPTO_PLUGIN


@pytest.mark.asyncio
async def test_ollama_copilot_llm_client_success():
    """Проверяет успешную генерацию подсказки Copilot через Ollama."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "summary": "Проблема с регистрацией контракта",
        "suggested_line_code": "L1",
        "suggested_response": "Здравствуйте! Проверьте вкладку контрактов.",
        "recommended_chunk_ids": ["chunk_contract_sec1"],
    }

    client = OllamaCopilotLlmClient(llm_client=mock_llm)
    result = await client.generate_copilot_summary(prompt="История диалога...")

    assert result.summary == "Проблема с регистрацией контракта"
    assert result.suggested_line_code == "L1"
    assert "вкладку контрактов" in result.suggested_response
    assert result.recommended_chunk_ids == ["chunk_contract_sec1"]


@pytest.mark.asyncio
async def test_ollama_copilot_llm_client_fallback_on_timeout():
    """Проверяет переход Copilot на резервную заглушку при таймауте модели."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.side_effect = TimeoutError("Ollama timeout")

    fallback = MockCopilotLlmClient()
    client = OllamaCopilotLlmClient(
        llm_client=mock_llm, fallback_client=fallback
    )

    # Промпт с маркером споров и ФАС
    prompt = "Клиент: Мы подаем жалобу в ФАС и суд!"
    result = await client.generate_copilot_summary(prompt=prompt)

    # Резервная заглушка должна рекомендовать линию L3
    assert result.suggested_line_code == "L3"
    assert "ФАС" in result.summary or "претензионной" in result.summary
