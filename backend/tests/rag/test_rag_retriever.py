from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient

from src.core.config import settings
from src.kb.qdrant import EmbeddingStub, init_knowledge_base_collection
from src.rag.retriever import Retriever
from src.rag.schemas import RagSourceChunkSchema


@pytest.fixture
async def client() -> AsyncQdrantClient:
    client = AsyncQdrantClient(":memory:")
    await init_knowledge_base_collection(client)

    embedding_stub = EmbeddingStub()
    point = embedding_stub.create_point(
        chunk_id="01",
        text="Контракт продлевается при условии что клиент..",
        payload={
            "doc_id": "01",
            "title": "Продление контракта",
            "status": "ACTIVE",
            "kb_type": "guide",
            "node_id": "1",
            "section_path": "1",
            "article_no": "1",
        },
    )
    await client.upsert(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points=[point],
    )
    return client


@pytest.fixture
def query() -> str:
    return "Как продлить контракт?"


async def test_retriever_retrieve(
    client: AsyncQdrantClient, query: str
) -> None:
    retriever = Retriever(
        embedding_model=EmbeddingStub(),
        top_k=1,
        qdrant_client=client,
    )
    result = await retriever.retrieve(query)

    assert isinstance(result, list)
    assert len(result) == 1
    chunk = result[0]
    assert isinstance(chunk, RagSourceChunkSchema)

    assert chunk.chunk_id == "01"
    assert chunk.doc_id == "01"
    assert chunk.title == "Продление контракта"
    assert chunk.quote_text == "Контракт продлевается при условии что клиент.."

    assert chunk.relevance_score is not None
    assert chunk.relevance_score > 0.0


async def test_retriever_respects_top_k(client: AsyncQdrantClient) -> None:
    embedding_stub = EmbeddingStub()
    points = [
        embedding_stub.create_point(
            chunk_id=f"0{i}",
            text=f"Дополнительный регламент {i}",
            payload={"doc_id": f"0{i}", "title": f"Регламент {i}"},
        )
        for i in range(2, 5)
    ]
    await client.upsert(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points=points,
    )

    retriever = Retriever(
        embedding_model=embedding_stub,
        top_k=2,
        qdrant_client=client,
    )
    result = await retriever.retrieve("Какой-то регламент")
    assert len(result) == 2


async def test_retriever_handles_qdrant_error() -> None:
    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.query_points.side_effect = RuntimeError(
        "Qdrant connection timeout"
    )

    retriever = Retriever(
        embedding_model=EmbeddingStub(),
        top_k=5,
        qdrant_client=mock_client,
    )
    result = await retriever.retrieve("любой запрос")
    assert result == []
