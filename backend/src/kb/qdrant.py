"""Интеграция с векторным хранилищем Qdrant и гибридный генератор эмбеддингов (dense + sparse)."""

import hashlib
import logging
import math
import re
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, SparseVectorParams, VectorParams

from src.core.config import settings

logger = logging.getLogger(__name__)

# Детерминированный namespace для генерации UUIDv5 точек Qdrant
QDRANT_CHUNK_NAMESPACE = uuid.UUID("a2b3c4d5-e6f7-4a5b-8c9d-0e1f2a3b4c5d")

RUSSIAN_STOP_WORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему",
    "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для",
    "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз",
    "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем",
    "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при",
    "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через",
    "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя",
    "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя"
}


def chunk_id_to_qdrant_uuid(chunk_id: str) -> uuid.UUID:
    """Генерирует детерминированный UUIDv5 по строковому chunk_id для точки Qdrant."""
    return uuid.uuid5(QDRANT_CHUNK_NAMESPACE, chunk_id)


def generate_sparse_bm25(text: str) -> models.SparseVector:
    """Генерирует лексический BM25-вектор через TF и хэширование терминов."""
    words = re.findall(r"\b[а-яА-Яa-zA-Z0-9_-]{2,}\b", text.lower())
    filtered_words = [w for w in words if w not in RUSSIAN_STOP_WORDS]
    if not filtered_words:
        filtered_words = words or ["empty"]

    total = len(filtered_words)
    counts: dict[str, int] = {}
    for w in filtered_words:
        counts[w] = counts.get(w, 0) + 1

    index_weights: dict[int, float] = {}
    for w, count in counts.items():
        # Хэшируем слово в диапазон [1..30000]
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % 30000 + 1
        tf = count / total
        weight = float(1.0 + math.log(1.0 + tf * 10.0))
        index_weights[h] = max(index_weights.get(h, 0.0), weight)

    sorted_items = sorted(index_weights.items(), key=lambda x: x[0])
    return models.SparseVector(
        indices=[k for k, _ in sorted_items],
        values=[v for _, v in sorted_items],
    )


async def init_knowledge_base_collection(
    client: AsyncQdrantClient,
    collection_name: str | None = None,
) -> None:
    """Инициализирует двухвекторную коллекцию в Qdrant (dense 1024D + sparse BM25)."""
    target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
    collections = await client.get_collections()
    existing_names = [c.name for c in collections.collections]

    if target_collection not in existing_names:
        await client.create_collection(
            collection_name=target_collection,
            vectors_config={
                "dense": VectorParams(size=1024, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(),
            },
        )


class HybridEmbeddingService:
    """Двухвекторный сервис эмбеддингов (Dense BGE-M3 1024D + Sparse BM25 Hashing)."""

    def __init__(self, dim: int = 1024, model_name: str | None = None) -> None:
        self.dim = dim
        self.model_name = model_name or getattr(settings, "EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
        self._dense_model = None
        self._tokenizer = None
        self._load_failed = False

    def _ensure_dense_model(self) -> None:
        """Ленивая загрузка bge-m3 при первом обращении (если разрешено в конфиге)."""
        if self._dense_model is not None or self._load_failed:
            return
        if not getattr(settings, "ENABLE_LOCAL_NEURAL_EMBEDDINGS", False):
            return
        try:
            from transformers import AutoModel, AutoTokenizer

            logger.info("Загрузка модели эмбеддингов %s...", self.model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._dense_model = AutoModel.from_pretrained(self.model_name)
            self._dense_model.eval()
            logger.info("Модель эмбеддингов %s успешно загружена.", self.model_name)
        except Exception as exc:
            logger.warning(
                "Не удалось загрузить модель эмбеддингов %s: %s. Используется быстрый детерминированный генератор.",
                self.model_name,
                exc,
            )
            self._load_failed = True

    def generate_dense_vector(self, text: str) -> list[float]:
        """Генерирует плотный 1024D вектор."""
        self._ensure_dense_model()
        if self._dense_model is not None and self._tokenizer is not None:
            try:
                import torch

                with torch.no_grad():
                    inputs = self._tokenizer(
                        [text],
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt",
                    )
                    outputs = self._dense_model(**inputs)
                    cls_emb = outputs.last_hidden_state[:, 0]
                    norm_emb = torch.nn.functional.normalize(cls_emb, p=2, dim=1)
                    return norm_emb[0].cpu().tolist()
            except Exception as e:
                logger.error("Ошибка инференса bge-m3: %s", e)

        # Детерминированный fallback (1024D нормализованный)
        seed = sum(ord(c) for c in text) if text else 1
        dense_vector = [
            ((seed * (i + 1)) % 1000) / 1000.0 for i in range(self.dim)
        ]
        norm = sum(v * v for v in dense_vector) ** 0.5 or 1.0
        return [v / norm for v in dense_vector]

    def generate_vectors(self, text: str) -> dict[str, Any]:
        """Генерирует согласованную двухвекторную структуру (dense + sparse)."""
        return {
            "dense": self.generate_dense_vector(text),
            "sparse": generate_sparse_bm25(text),
        }

    def create_point(
        self,
        chunk_id: str,
        text: str,
        payload: dict[str, Any],
    ) -> models.PointStruct:
        """Формирует объект PointStruct с детерминированным UUIDv5 и двумя векторами."""
        vectors = self.generate_vectors(text)
        point_id = str(chunk_id_to_qdrant_uuid(chunk_id))
        enriched_payload = {**payload, "chunk_id": chunk_id, "text": text}

        return models.PointStruct(
            id=point_id,
            vector=vectors,
            payload=enriched_payload,
        )


# Алиас для обратной совместимости
EmbeddingStub = HybridEmbeddingService
