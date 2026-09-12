"""Асинхронный клиент инференса языковых моделей (Ollama / OpenAI-compatible)."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class OllamaStreamClient:
    """Асинхронный клиент потоковой генерации токенов через Ollama HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Инициализирует подключение к инференс-серверу Ollama."""
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.default_timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float | None = None,
    ) -> AsyncIterator[str]:
        """Потоковая генерация ответа модели по протоколу NDJSON."""
        request_timeout = timeout or self.default_timeout
        endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        # Таймаут на соединение 5с, общий таймаут на стриминг
        timeout_config = httpx.Timeout(request_timeout, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                async with client.stream("POST", endpoint, json=payload) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        logger.error(
                            f"Ollama API вернул статус {response.status_code}: {error_body.decode('utf-8', errors='replace')}"
                        )
                        raise RuntimeError(
                            f"Ollama API error: status {response.status_code}"
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue

            except (httpx.ConnectError, httpx.ConnectTimeout) as err:
                logger.error(
                    f"Не удалось подключиться к Ollama по адресу {self.base_url}: {err}. "
                    f"Проверьте, запущен ли Ollama на RTX 4060 хосте с OLLAMA_HOST=0.0.0.0."
                )
                raise ConnectionError(
                    f"Ollama host unreachable at {self.base_url}"
                ) from err
            except httpx.ReadTimeout as err:
                logger.error(f"Превышен таймаут чтения потока Ollama ({request_timeout}s): {err}")
                raise TimeoutError("Ollama stream read timeout") from err


def get_llm_stream_client() -> OllamaStreamClient:
    """Фабрика получения настроенного экземпляра OllamaStreamClient."""
    return OllamaStreamClient(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )
