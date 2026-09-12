"""
Пайплайн индексации базы знаний на GPU (ADR-0001: Small-to-Big Retrieval).

1. Парсит нормативные документы (.md) по заголовкам (#, ##, ###, ####),
   сохраняя таблицы в формате Markdown неделимыми блоками.
2. Сохраняет родительские узлы AST в PostgreSQL (kb_documents, kb_nodes).
3. Нарезает родительские узлы на дочерние чанки (200-350 токенов, overlap 10-15%).
4. Векторизует дочерние чанки на GPU (CUDA) моделью BAAI/bge-m3 (1024D).
5. Загружает точки в Qdrant (коллекция 'tender_chunks') со строго минималистичным
   payload: {chunk_id, node_id, document_id, section_path}.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import tiktoken
import torch
import torch.nn.functional as F
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy import delete
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

from src.core.config import settings
from src.db.database import async_session_maker
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kb.ingest_adr0001")

COLLECTION_NAME = "tender_chunks"
TARGET_DOCUMENTS = [
    (
        "instruktsiya_po_elektronnomu_aktirovaniyu.md",
        "Инструкция по электронному актированию",
    ),
    ("instruktsiya_po_formirovaniyu_yml.md", "Инструкция по формированию YML"),
    (
        "instruktsiya_po_rabote_s_mashinochitaemymi_doverennostyami.md",
        "Инструкция по работе с машиночитаемыми доверенностями",
    ),
    (
        "instruktsiya_po_rabote_s_portalom_dlya_postavshchika.md",
        "Инструкция по работе с Порталом для поставщика",
    ),
    (
        "instruktsiya_po_rabote_s_portalom_dlya_zakazchika.md",
        "Инструкция по работе с Порталом для заказчика",
    ),
    (
        "instruktsiya_po_sozdaniyu_oferty_i_ste.md",
        "Инструкция по созданию оферты и СТЕ",
    ),
    ("temy_podtemy_obrashcheniy.md", "Классификатор тем и подтем обращений"),
]

UUID_NAMESPACE = uuid.UUID("7f3a9e10-c4b2-4d1a-8c5e-9a7b6d5e4f3a")


class TokenizerHelper:
    def __init__(self, encoding_name: str = "cl100k_base"):
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            self.encoding = None

    def count_tokens(self, text_str: str) -> int:
        if not text_str or not text_str.strip():
            return 0
        if self.encoding is not None:
            return len(self.encoding.encode(text_str, disallowed_special=()))
        words = re.findall(r"\w+|[^\w\s]", text_str, re.UNICODE)
        return max(1, round(len(words) * 1.35))


def extract_table_blocks(content: str) -> list[tuple[bool, str]]:
    """Разделяет текст на блоки обычного текста и неделимые блоки таблиц Markdown."""
    lines = content.split("\n")
    blocks: list[tuple[bool, str]] = []
    current_table: list[str] = []
    current_text: list[str] = []
    in_table = False

    table_row_pattern = re.compile(r"^\s*\|.*\|\s*$")

    for line in lines:
        is_row = bool(table_row_pattern.match(line))
        if is_row:
            if not in_table:
                if current_text:
                    text_content = "\n".join(current_text).strip()
                    if text_content:
                        blocks.append((False, text_content))
                    current_text = []
                in_table = True
            current_table.append(line)
        else:
            if in_table:
                table_content = "\n".join(current_table).strip()
                if table_content:
                    blocks.append((True, table_content))
                current_table = []
                in_table = False
            current_text.append(line)

    if in_table and current_table:
        table_content = "\n".join(current_table).strip()
        if table_content:
            blocks.append((True, table_content))
    elif current_text:
        text_content = "\n".join(current_text).strip()
        if text_content:
            blocks.append((False, text_content))

    return blocks


class MarkdownAstParser:
    """Парсит Markdown-файл по заголовкам (#, ##, ###, ####) в родительские узлы AST."""

    def __init__(self, tokenizer_helper: TokenizerHelper):
        self.tok = tokenizer_helper

    def parse_markdown(
        self,
        doc_id: str,
        doc_title: str,
        markdown_text: str,
        is_faq: bool = False,
    ) -> list[dict[str, Any]]:
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        lines = markdown_text.split("\n")

        raw_sections: list[dict[str, Any]] = []
        current_level = 1
        current_title = doc_title
        current_lines: list[str] = []
        inside_code_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_code_block = not inside_code_block
                current_lines.append(line)
                continue

            if not inside_code_block:
                match = heading_pattern.match(line)
                if match:
                    hashes, title_text = match.groups()
                    level = len(hashes)
                    raw_sections.append(
                        {
                            "level": current_level,
                            "title": current_title,
                            "lines": current_lines,
                        }
                    )
                    current_level = level
                    current_title = title_text.strip()
                    current_lines = []
                    continue

            current_lines.append(line)

        raw_sections.append(
            {
                "level": current_level,
                "title": current_title,
                "lines": current_lines,
            }
        )

        nodes: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = []

        for idx, sec in enumerate(raw_sections):
            content = "\n".join(sec["lines"]).strip()
            title = sec["title"]
            level_num = sec["level"]

            if idx == 0 and not content:
                continue

            while stack and stack[-1]["level"] >= level_num:
                stack.pop()

            parent_node_id = stack[-1]["node_id"] if stack else None

            path_components = [item["title"] for item in stack] + [title]
            section_path = " > ".join(path_components)

            node_id = str(
                uuid.uuid5(UUID_NAMESPACE, f"{doc_id}_node_{idx}_{title[:30]}")
            )

            if is_faq:
                db_level = "faq"
            elif level_num == 1:
                db_level = "section"
            elif level_num == 2:
                db_level = "article"
            else:
                db_level = "item"

            token_count = self.tok.count_tokens(content)

            node_data = {
                "node_id": node_id,
                "doc_id": doc_id,
                "parent_node_id": parent_node_id,
                "level": db_level,
                "section_path": section_path,
                "title": title,
                "full_content": content if content else f"### {title}",
                "token_count": token_count,
                "level_num": level_num,
            }

            nodes.append(node_data)
            stack.append(
                {"level": level_num, "node_id": node_id, "title": title}
            )

        return nodes


class ChildChunker:
    """Нарезка родительских узлов на дочерние чанки (200-350 токенов, overlap 10-15%)."""

    def __init__(
        self,
        tokenizer_helper: TokenizerHelper,
        min_tokens: int = 200,
        max_tokens: int = 350,
    ):
        self.tok = tokenizer_helper
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens

    def slice_node_to_chunks(
        self, node: dict[str, Any]
    ) -> list[dict[str, Any]]:
        full_content = node["full_content"]
        node_id = node["node_id"]
        doc_id = node["doc_id"]
        section_path = node["section_path"]

        total_tokens = self.tok.count_tokens(full_content)
        if total_tokens <= self.max_tokens:
            chunk_id = str(uuid.uuid5(UUID_NAMESPACE, f"{node_id}_c0"))
            return [
                {
                    "chunk_id": chunk_id,
                    "node_id": node_id,
                    "document_id": doc_id,
                    "section_path": section_path,
                    "text": full_content,
                    "token_count": total_tokens,
                }
            ]

        blocks = extract_table_blocks(full_content)
        atomic_units: list[str] = []

        for is_table, block_content in blocks:
            if is_table:
                atomic_units.append(block_content)
            else:
                paragraphs = [
                    p.strip() for p in block_content.split("\n\n") if p.strip()
                ]
                for para in paragraphs:
                    para_tokens = self.tok.count_tokens(para)
                    if para_tokens <= self.max_tokens:
                        atomic_units.append(para)
                    else:
                        sentences = re.split(r"(?<=[.!?])\s+", para)
                        sent_buf: list[str] = []
                        sent_buf_tokens = 0
                        for s in sentences:
                            s_tokens = self.tok.count_tokens(s)
                            if sent_buf_tokens + s_tokens <= self.max_tokens:
                                sent_buf.append(s)
                                sent_buf_tokens += s_tokens
                            else:
                                if sent_buf:
                                    atomic_units.append(" ".join(sent_buf))
                                    sent_buf = []
                                    sent_buf_tokens = 0
                                if s_tokens > self.max_tokens:
                                    words = s.split()
                                    w_buf: list[str] = []
                                    for w in words:
                                        w_buf.append(w)
                                        if (
                                            self.tok.count_tokens(
                                                " ".join(w_buf)
                                            )
                                            >= self.max_tokens - 15
                                        ):
                                            atomic_units.append(
                                                " ".join(w_buf)
                                            )
                                            w_buf = []
                                    if w_buf:
                                        sent_buf.append(" ".join(w_buf))
                                        sent_buf_tokens = (
                                            self.tok.count_tokens(
                                                " ".join(w_buf)
                                            )
                                        )
                                else:
                                    sent_buf.append(s)
                                    sent_buf_tokens = s_tokens
                        if sent_buf:
                            atomic_units.append(" ".join(sent_buf))

        chunks: list[dict[str, Any]] = []
        current_units: list[str] = []
        current_tokens = 0

        for unit in atomic_units:
            unit_tokens = self.tok.count_tokens(unit)
            if current_tokens + unit_tokens <= self.max_tokens:
                current_units.append(unit)
                current_tokens += unit_tokens
            else:
                if current_units:
                    chunk_text = "\n\n".join(current_units)
                    chunk_id = str(
                        uuid.uuid5(UUID_NAMESPACE, f"{node_id}_c{len(chunks)}")
                    )
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "node_id": node_id,
                            "document_id": doc_id,
                            "section_path": section_path,
                            "text": chunk_text,
                            "token_count": current_tokens,
                        }
                    )

                    # Вычисляем overlap 10-15% (берем последний блок)
                    overlap_unit = current_units[-1] if current_units else ""
                    overlap_tokens = self.tok.count_tokens(overlap_unit)
                    if overlap_tokens <= int(self.max_tokens * 0.25):
                        current_units = [overlap_unit, unit]
                        current_tokens = overlap_tokens + unit_tokens
                    else:
                        current_units = [unit]
                        current_tokens = unit_tokens
                else:
                    current_units = [unit]
                    current_tokens = unit_tokens

        if current_units:
            chunk_text = "\n\n".join(current_units)
            chunk_id = str(
                uuid.uuid5(UUID_NAMESPACE, f"{node_id}_c{len(chunks)}")
            )
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "node_id": node_id,
                    "document_id": doc_id,
                    "section_path": section_path,
                    "text": chunk_text,
                    "token_count": current_tokens,
                }
            )

        return chunks


class GpuEmbedder:
    """Векторизация текстов моделью BAAI/bge-m3 на GPU (Ollama Vulkan/ROCm или PyTorch CUDA)."""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self.use_ollama = False
        self.ollama_url = os.getenv(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        )

        # Проверяем доступность локального Ollama с bge-m3
        try:
            import httpx

            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=3.0)
            if resp.status_code == 200:
                models = [
                    m.get("name", "") for m in resp.json().get("models", [])
                ]
                if any("bge-m3" in m for m in models):
                    self.use_ollama = True
                    logger.info(
                        f"Инициализация GpuEmbedder: используем аппаратный бэкенд Ollama GPU ({self.ollama_url})"
                    )
        except Exception as e:
            logger.debug(f"Ollama недоступен: {e}")

        if not self.use_ollama:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                f"Инициализация GpuEmbedder: модель {model_name}, устройство: {self.device}"
            )
            if self.device == "cuda":
                logger.info(
                    f"Используемый GPU: {torch.cuda.get_device_name(0)}"
                )

            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name).to(self.device)
            self.model.eval()

    def embed_batches(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        total = len(texts)

        if self.use_ollama:
            import httpx

            with tqdm(
                total=total,
                desc="GPU Векторизация чанков (Ollama)",
                unit="chunk",
            ) as pbar:
                for i in range(0, total, batch_size):
                    batch_texts = texts[i : i + batch_size]
                    try:
                        resp = httpx.post(
                            f"{self.ollama_url}/api/embed",
                            json={"model": "bge-m3", "input": batch_texts},
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                        embs = resp.json()["embeddings"]
                        all_embeddings.extend(embs)
                    except Exception as err:
                        logger.error(
                            f"Ошибка Ollama embed: {err}, повтор по 1 элементу..."
                        )
                        for single_t in batch_texts:
                            r = httpx.post(
                                f"{self.ollama_url}/api/embed",
                                json={"model": "bge-m3", "input": single_t},
                                timeout=60.0,
                            )
                            r.raise_for_status()
                            all_embeddings.append(r.json()["embeddings"][0])
                    pbar.update(len(batch_texts))
            return all_embeddings

        with tqdm(
            total=total, desc="GPU Векторизация чанков", unit="chunk"
        ) as pbar:
            for i in range(0, total, batch_size):
                batch_texts = texts[i : i + batch_size]
                inputs = self.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=8192,
                    return_tensors="pt",
                ).to(self.device)

                with torch.no_grad():
                    outputs = self.model(**inputs)
                    cls_embeddings = outputs.last_hidden_state[:, 0]
                    norm_embeddings = F.normalize(cls_embeddings, p=2, dim=-1)
                    batch_vectors = norm_embeddings.cpu().tolist()
                    all_embeddings.extend(batch_vectors)

                pbar.update(len(batch_texts))

        return all_embeddings


async def init_qdrant_collection(
    client: AsyncQdrantClient, collection_name: str = COLLECTION_NAME
) -> None:
    """Создает или пересоздает коллекцию tender_chunks в Qdrant."""
    collections = await client.get_collections()
    existing_names = [c.name for c in collections.collections]

    if collection_name not in existing_names:
        logger.info(
            f"Создание новой коллекции Qdrant: {collection_name} (1024D Cosine)"
        )
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=1024,
                distance=qmodels.Distance.COSINE,
            ),
        )
    else:
        logger.info(f"Коллекция Qdrant {collection_name} уже существует.")


async def run_pipeline():
    logger.info(
        "=== СТАРТ GPU ПАЙПЛАЙНА ИНДЕКСАЦИИ (ADR-0001: SMALL-TO-BIG) ==="
    )
    start_time = time.time()

    # 1. Проверка окружения
    logger.info(
        f"PyTorch version: {torch.__version__}, CUDA available: {torch.cuda.is_available()}"
    )
    if torch.cuda.is_available():
        logger.info(f"CUDA Device: {torch.cuda.get_device_name(0)}")

    tok_helper = TokenizerHelper()
    parser = MarkdownAstParser(tok_helper)
    chunker = ChildChunker(tok_helper, min_tokens=200, max_tokens=350)

    # 2. Поиск директории с документами
    kb_dir = settings.KB_STORAGE_DIR
    if not kb_dir.exists():
        # Фолбэк на относительный путь
        kb_dir = Path("storage/kb_documents")
    if not kb_dir.exists():
        kb_dir = Path("/app/storage/kb_documents")

    logger.info(f"Каталог документов базы знаний: {kb_dir.resolve()}")

    all_doc_records: list[KbDocumentModel] = []
    all_node_records: list[KbNodeModel] = []
    all_chunk_records: list[KbChunkModel] = []
    all_chunks_payloads: list[dict[str, Any]] = []

    # 3. Парсинг каждого документа
    for filename, doc_title in TARGET_DOCUMENTS:
        file_path = kb_dir / filename
        if not file_path.exists():
            logger.warning(f"Файл {filename} не найден в {kb_dir}, пропуск.")
            continue

        logger.info(f"Обработка документа: {filename} ('{doc_title}')")
        content = file_path.read_text(encoding="utf-8")
        doc_id = str(uuid.uuid5(UUID_NAMESPACE, filename))

        is_faq = "temy_podtemy" in filename.lower()
        nodes_data = parser.parse_markdown(
            doc_id=doc_id,
            doc_title=doc_title,
            markdown_text=content,
            is_faq=is_faq,
        )

        doc_model = KbDocumentModel(
            doc_id=doc_id,
            title=doc_title,
            regime="MOS_PORTAL",
            status="indexed",
            error_message=None,
            source_url=filename,
        )
        all_doc_records.append(doc_model)

        doc_chunks_count = 0
        for n_data in nodes_data:
            node_model = KbNodeModel(
                node_id=n_data["node_id"],
                doc_id=doc_id,
                parent_node_id=n_data["parent_node_id"],
                level=n_data["level"],
                section_path=n_data["section_path"],
                article_no=None,
                part_no=None,
                title=n_data["title"],
                full_content=n_data["full_content"],
                table_md=None,
                token_count=n_data["token_count"],
            )
            all_node_records.append(node_model)

            # Нарезка дочерних чанков
            sliced_chunks = chunker.slice_node_to_chunks(n_data)
            for c in sliced_chunks:
                chunk_model = KbChunkModel(
                    chunk_id=c["chunk_id"],
                    node_id=c["node_id"],
                    text=c["text"],
                    context_prefix=None,
                    hyp_questions=[],
                    embedding_model_version="bge-m3",
                )
                all_chunk_records.append(chunk_model)
                all_chunks_payloads.append(c)
                doc_chunks_count += 1

        logger.info(
            f"  -> Секций AST: {len(nodes_data)}, Дочерних чанков: {doc_chunks_count}"
        )

    total_nodes = len(all_node_records)
    total_chunks = len(all_chunks_payloads)
    logger.info(
        f"ИТОГО: {len(all_doc_records)} документов, {total_nodes} узлов AST, {total_chunks} дочерних чанков."
    )

    # 4. Сохранение в PostgreSQL (Топологический порядок)
    logger.info("Сохранение в PostgreSQL...")
    async with async_session_maker() as session:
        # Очищаем старые записи
        await session.execute(delete(KbChunkModel))
        await session.execute(delete(KbNodeModel))
        await session.execute(delete(KbDocumentModel))
        await session.commit()

        # 4.1 Документы
        for doc in all_doc_records:
            session.add(doc)
        await session.flush()

        # 4.2 Узлы AST: топологически (сначала parent_node_id is None, затем дети)
        root_nodes = [n for n in all_node_records if n.parent_node_id is None]
        child_nodes = [
            n for n in all_node_records if n.parent_node_id is not None
        ]

        for n in root_nodes:
            session.add(n)
        await session.flush()

        # Послойная вставка дочерних узлов
        inserted_ids = {n.node_id for n in root_nodes}
        remaining_children = child_nodes
        while remaining_children:
            batch = [
                n
                for n in remaining_children
                if n.parent_node_id in inserted_ids
            ]
            if not batch:
                # Если цикличность или пропущен родитель, вставляем все оставшиеся
                batch = remaining_children
            for n in batch:
                session.add(n)
                inserted_ids.add(n.node_id)
            await session.flush()
            remaining_children = [
                n for n in remaining_children if n.node_id not in inserted_ids
            ]

        # 4.3 Чанки
        for c in all_chunk_records:
            session.add(c)

        await session.commit()
        logger.info("Успешно зафиксировано в PostgreSQL.")

    # 5. GPU Векторизация моделью BAAI/bge-m3
    embedder = GpuEmbedder()
    chunk_texts = [c["text"] for c in all_chunks_payloads]
    vectors = embedder.embed_batches(chunk_texts, batch_size=32)

    # 6. Загрузка в Qdrant
    qdrant_host = os.getenv("QDRANT_HOST", settings.QDRANT_HOST)
    qdrant_port = int(os.getenv("QDRANT_PORT", settings.QDRANT_PORT))
    logger.info(f"Подключение к Qdrant ({qdrant_host}:{qdrant_port})...")
    qdrant_client = AsyncQdrantClient(host=qdrant_host, port=qdrant_port)

    await init_qdrant_collection(qdrant_client, COLLECTION_NAME)

    # Формирование точек со строго минималистичным payload
    qdrant_points: list[qmodels.PointStruct] = []
    for c, vec in zip(all_chunks_payloads, vectors, strict=True):
        qdrant_points.append(
            qmodels.PointStruct(
                id=c["chunk_id"],
                vector=vec,
                payload={
                    "chunk_id": c["chunk_id"],
                    "node_id": c["node_id"],
                    "document_id": c["document_id"],
                    "section_path": c["section_path"],
                },
            )
        )

    # Пакетная загрузка в Qdrant
    batch_size = 64
    logger.info(
        f"Загрузка {len(qdrant_points)} точек в коллекцию '{COLLECTION_NAME}'..."
    )
    with tqdm(
        total=len(qdrant_points), desc="Qdrant Upsert", unit="point"
    ) as pbar:
        for i in range(0, len(qdrant_points), batch_size):
            batch = qdrant_points[i : i + batch_size]
            await qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch,
            )
            pbar.update(len(batch))

    await qdrant_client.close()

    elapsed = time.time() - start_time
    logger.info(f"=== ИНДЕКСАЦИЯ УСПЕШНО ЗАВЕРШЕНА ЗА {elapsed:.2f} сек ===")
    logger.info(
        f"ИТОГ: {len(all_doc_records)} документов, {total_nodes} узлов AST, {len(qdrant_points)} векторных точек."
    )


if __name__ == "__main__":
    asyncio.run(run_pipeline())
