"""Клиент векторного хранилища Qdrant."""

import logging
import os

from qdrant_client import AsyncQdrantClient

from src.core.config import settings

logger = logging.getLogger(__name__)

_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient | None:
    """Возвращает синглтон асинхронного клиента Qdrant."""
    global _qdrant_client
    if _qdrant_client is None:
        # Защита от поврежденного пути в SSL_CERT_FILE (если указывает на каталог)
        ssl_cert = os.environ.get("SSL_CERT_FILE")
        if ssl_cert and not os.path.isfile(ssl_cert):
            os.environ.pop("SSL_CERT_FILE", None)

        try:
            _qdrant_client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                grpc_port=settings.QDRANT_GRPC_PORT,
                prefer_grpc=False,
            )
        except Exception as exc:
            logger.warning(
                "Не удалось инициализировать Qdrant клиент: %s", exc
            )
            return None
    return _qdrant_client
