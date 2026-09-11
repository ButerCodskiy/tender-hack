"""Модульные тесты базовых моделей, топологии и векторной интеграции базы знаний (kb)."""

import uuid

from qdrant_client.http import models

from src.kb.chunker import HierarchicalChunker, TokenCounter
from src.kb.models import KbNodeModel
from src.kb.qdrant import (
    QDRANT_CHUNK_NAMESPACE,
    EmbeddingStub,
    chunk_id_to_qdrant_uuid,
)
from src.kb.repository import topological_sort_nodes
from src.kb.schemas import ParsedNodeSchema


def test_chunk_id_to_qdrant_uuid_deterministic() -> None:
    """Проверяет детерминированность генерации UUIDv5 по строковому chunk_id."""
    chunk_id = "chunk_portal_zakupki_reglament_sec4_p1"
    uuid1 = chunk_id_to_qdrant_uuid(chunk_id)
    uuid2 = chunk_id_to_qdrant_uuid(chunk_id)

    assert isinstance(uuid1, uuid.UUID)
    assert uuid1 == uuid2
    assert uuid1 == uuid.uuid5(QDRANT_CHUNK_NAMESPACE, chunk_id)


def test_embedding_stub_dense_and_sparse_vectors() -> None:
    """Проверяет генерацию двухвекторной структуры (dense 1024D + sparse models.SparseVector)."""
    stub = EmbeddingStub(dim=1024)
    text = "Протокол разногласий подписывается в личном кабинете поставщика с помощью ЭЦП."
    vectors = stub.generate_vectors(text)

    # 1. Проверка плотного вектора
    assert "dense" in vectors
    assert len(vectors["dense"]) == 1024
    assert isinstance(vectors["dense"][0], float)

    # 2. Проверка разреженного вектора
    assert "sparse" in vectors
    sparse = vectors["sparse"]
    assert isinstance(sparse, models.SparseVector)
    assert len(sparse.indices) > 0
    assert len(sparse.values) == len(sparse.indices)

    # 3. Проверка формирования структуры точки PointStruct
    point = stub.create_point(
        chunk_id="test_chunk_01",
        text=text,
        payload={"doc_id": "doc_test"},
    )
    assert point.id == str(chunk_id_to_qdrant_uuid("test_chunk_01"))
    assert point.payload["chunk_id"] == "test_chunk_01"
    assert point.payload["doc_id"] == "doc_test"


def test_topological_sort_nodes() -> None:
    """Проверяет топологическую сортировку узлов AST (родитель перед ребенком)."""
    # Создаем узлы в обратном/хаотичном порядке
    item_node = KbNodeModel(
        node_id="node_item_4_1",
        doc_id="doc_1",
        parent_node_id="node_sec_4",
        level="item",
        section_path="Sec 4 / Item 4.1",
        title="Пункт 4.1",
        full_content="Текст пункта",
        token_count=10,
    )
    sec_node = KbNodeModel(
        node_id="node_sec_4",
        doc_id="doc_1",
        parent_node_id="node_root",
        level="section",
        section_path="Sec 4",
        title="Раздел 4",
        full_content="Текст раздела",
        token_count=20,
    )
    root_node = KbNodeModel(
        node_id="node_root",
        doc_id="doc_1",
        parent_node_id=None,
        level="document",
        section_path="Root",
        title="Корень",
        full_content="Вводная часть",
        token_count=15,
    )

    unordered = [item_node, sec_node, root_node]
    sorted_nodes = topological_sort_nodes(unordered)

    node_ids = [n.node_id for n in sorted_nodes]
    # root_node обязан быть раньше sec_node, а sec_node раньше item_node
    assert node_ids.index("node_root") < node_ids.index("node_sec_4")
    assert node_ids.index("node_sec_4") < node_ids.index("node_item_4_1")


def test_tiktoken_counter() -> None:
    """Проверяет локальный подсчет токенов через tiktoken (cl100k_base)."""
    counter = TokenCounter(encoding_name="cl100k_base")
    text = "Порядок подписания протокола разногласий на Портале поставщиков."
    token_count = counter.count_tokens(text)

    assert token_count > 0
    assert counter.count_tokens("") == 0
    assert counter.count_tokens("   ") == 0


def test_hierarchical_chunker_overlap_zero_and_tail_merge() -> None:
    """Проверяет нарезку чанкером узла без перекрытия и подклейку коротких хвостов."""
    chunker = HierarchicalChunker(max_tokens=25, min_tail_tokens=5)
    node = ParsedNodeSchema(
        node_id="node_test_01",
        doc_id="doc_01",
        parent_node_id=None,
        level="section",
        section_path="Раздел 1",
        title="Заголовок",
        full_content=(
            "Первое предложение регламента котировочных сессий. "
            "Второе предложение с описанием сроков подачи заявок. "
            "Третье предложение о порядке подписания контракта. "
            "Четвертое предложение о возврате обеспечения заявки."
        ),
        token_count=40,
    )

    chunks = chunker.chunk_node(node)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.chunk_id.startswith("node_test_01_c")
        assert c.node_id == "node_test_01"
        assert len(c.text) > 0
