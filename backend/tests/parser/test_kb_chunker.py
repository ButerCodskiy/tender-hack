"""
Тесты иерархического чанкинга и токенизации (test_kb_chunker.py).
"""

from src.kb.chunker import HierarchicalChunker, TokenCounter
from src.kb.schemas import ParsedNodeSchema


def test_token_counter():
    tc = TokenCounter()
    cnt = tc.count_tokens("Проверка подсчета токенов для русского текста.")
    assert cnt > 0
    assert cnt == tc.count_tokens(
        "Проверка подсчета токенов для русского текста."
    )


def test_hierarchical_chunker_splitting_and_tail_merging():
    chunker = HierarchicalChunker(max_tokens=50, min_tail_tokens=20)

    # Генерируем текст из нескольких предложений
    long_text = " ".join(
        [
            f"Предложение номер {i} содержит полезные данные регламента."
            for i in range(1, 25)
        ]
    )

    node = ParsedNodeSchema(
        node_id="TEST_n01",
        doc_id="TEST_DOC",
        level="section",
        section_path="Раздел 1",
        title="Тестовый раздел",
        full_content=long_text,
        token_count=chunker.token_counter.count_tokens(long_text),
    )

    chunks = chunker.chunk_node(node)
    assert len(chunks) > 1

    # Проверяем, что размер каждого чанка не превышает разумных пределов
    for c in chunks:
        tok_count = chunker.token_counter.count_tokens(c.text)
        assert tok_count <= 80  # С учетом подклейки хвоста


def test_table_chunk_has_table_flag():
    chunker = HierarchicalChunker(max_tokens=100, min_tail_tokens=20)
    node = ParsedNodeSchema(
        node_id="TEST_TABLE_n01",
        doc_id="TEST_DOC",
        level="item",
        section_path="Раздел 1 > Таблица",
        title="Таблица регламента",
        full_content="Таблица",
        table_md="| A | B |\n|---|---|\n| 1 | 2 |",
        token_count=10,
    )

    linearized = [
        "Колонка 1: Значение 1; Колонка 2: Значение 2",
        "Колонка 1: Значение 3; Колонка 2: Значение 4",
    ]

    chunks = chunker.chunk_node(node, linearized_table_facts=linearized)
    # Текстовый чанк узла имеет has_table=False, а табличный чанк имеет has_table=True
    table_chunks = [c for c in chunks if c.has_table]
    assert len(table_chunks) >= 1
    assert "Значение 1" in table_chunks[0].text
