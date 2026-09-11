"""
Модуль иерархического чанкинга текста и таблиц (chunker.py).

Реализует:
1. Токенизацию с использованием словаря BAAI/bge-m3 (SentencePiece / XLM-RoBERTa)
   с автономным оффлайн-фолбэком (длина слов * 1.35).
   Tiktoken строго исключен во избежание раздувания токенов на кириллице.
2. Иерархическую нарезку текста узлов AST:
   - Максимальный размер чанка: 350 токенов.
   - Подклейка коротких хвостов: фрагмент < 80 токенов объединяется с предыдущим чанком.
3. Разметку признака has_table = True для табличных фактов под фильтрацию в Qdrant payload.
4. Формирование объектов ParsedChunkSchema, согласованных с DDL таблицы kb_chunks.
"""

import logging
import re
from typing import Any

import tiktoken

from src.kb.schemas import ParsedChunkSchema, ParsedNodeSchema

logger = logging.getLogger(__name__)


class TokenCounter:
    """Класс локального подсчета токенов на базе tiktoken (cl100k_base).

    Обеспечивает быстрый, детерминированный оффлайн-подсчет токенов без сетевых
    запросов к Hugging Face и тяжелых зависимостей transformers в тестах.
    """

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.encoding_name = encoding_name
        self._encoding: Any = None
        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception as exc:
            logger.warning(
                "Не удалось загрузить энкодинг tiktoken %s: %s",
                encoding_name,
                exc,
            )

    def count_tokens(self, text: str) -> int:
        """Возвращает точное количество токенов в тексте."""
        if not text or not text.strip():
            return 0

        if self._encoding is not None:
            return len(self._encoding.encode(text, disallowed_special=()))

        # Оффлайн-эвристика при сбое инициализации
        words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        return max(1, round(len(words) * 1.35))


class HierarchicalChunker:
    """
    Иерархический чанкер для узлов документа AST Docling.
    Нарезает текст узлов с сохранением семантических границ и ограничения 350 токенов.
    """

    def __init__(
        self,
        max_tokens: int = 350,
        min_tail_tokens: int = 80,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.min_tail_tokens = min_tail_tokens
        self.token_counter = token_counter or TokenCounter()

    def _split_into_sentences(self, text: str) -> list[str]:
        """Разбиение текста на предложения с сохранением пунктуации."""
        # Разделение по точкам, восклицательным и вопросительным знакам с последующим пробелом
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _split_text_to_chunks(self, text: str) -> list[str]:
        """
        Нарезка текста на фрагменты не более max_tokens с подклейкой хвостов < min_tail_tokens.
        """
        if not text.strip():
            return []

        total_tokens = self.token_counter.count_tokens(text)
        if total_tokens <= self.max_tokens:
            return [text.strip()]

        # Сначала пробуем разделить по параграфам (двойной перенос строки)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        pieces: list[str] = []

        for para in paragraphs:
            para_tokens = self.token_counter.count_tokens(para)
            if para_tokens <= self.max_tokens:
                pieces.append(para)
            else:
                # Если параграф больше лимита, дробим по предложениям
                sentences = self._split_into_sentences(para)
                curr_sentence_buf: list[str] = []
                curr_buf_tokens = 0

                for sent in sentences:
                    sent_tokens = self.token_counter.count_tokens(sent)
                    if curr_buf_tokens + sent_tokens <= self.max_tokens:
                        curr_sentence_buf.append(sent)
                        curr_buf_tokens += sent_tokens
                    else:
                        if curr_sentence_buf:
                            pieces.append(" ".join(curr_sentence_buf))
                            curr_sentence_buf = []
                            curr_buf_tokens = 0
                        # Если отдельное предложение превышает лимит, дробим по словам
                        if sent_tokens > self.max_tokens:
                            words = sent.split()
                            sub_words: list[str] = []
                            for w in words:
                                sub_words.append(w)
                                if (
                                    self.token_counter.count_tokens(
                                        " ".join(sub_words)
                                    )
                                    >= self.max_tokens - 10
                                ):
                                    pieces.append(" ".join(sub_words))
                                    sub_words = []
                            if sub_words:
                                curr_sentence_buf.append(" ".join(sub_words))
                                curr_buf_tokens = (
                                    self.token_counter.count_tokens(
                                        " ".join(sub_words)
                                    )
                                )
                        else:
                            curr_sentence_buf.append(sent)
                            curr_buf_tokens = sent_tokens

                if curr_sentence_buf:
                    pieces.append(" ".join(curr_sentence_buf))

        # Собираем фрагменты в чанки с соблюдением лимита max_tokens
        chunks: list[str] = []
        current_chunk_parts: list[str] = []
        current_chunk_tokens = 0

        for piece in pieces:
            piece_tokens = self.token_counter.count_tokens(piece)
            if current_chunk_tokens + piece_tokens <= self.max_tokens:
                current_chunk_parts.append(piece)
                current_chunk_tokens += piece_tokens
            else:
                if current_chunk_parts:
                    chunks.append("\n\n".join(current_chunk_parts))
                current_chunk_parts = [piece]
                current_chunk_tokens = piece_tokens

        if current_chunk_parts:
            chunks.append("\n\n".join(current_chunk_parts))

        # Применяем правило подклейки хвоста: если последний чанк < min_tail_tokens
        if len(chunks) > 1:
            last_tokens = self.token_counter.count_tokens(chunks[-1])
            if last_tokens < self.min_tail_tokens:
                # Склеиваем с предпоследним чанком
                tail = chunks.pop()
                chunks[-1] = chunks[-1] + "\n\n" + tail

        return chunks

    def chunk_node(
        self,
        node: ParsedNodeSchema,
        linearized_table_facts: list[str] | None = None,
    ) -> list[ParsedChunkSchema]:
        """
        Преобразование узла документа в список чанков ParsedChunkSchema.
        Если переданы линеаризованные факты таблицы, формирует чанки с флагом has_table = True.
        """
        chunks: list[ParsedChunkSchema] = []
        chunk_idx = 1

        is_table_node = bool(node.table_md or linearized_table_facts)

        # 1. Чанкинг табличных фактов (если переданы линеаризованные факты таблицы)
        if linearized_table_facts:
            table_chunks_text: list[str] = []
            curr_facts: list[str] = []
            curr_tokens = 0

            for fact in linearized_table_facts:
                fact_tokens = self.token_counter.count_tokens(fact)
                if curr_tokens + fact_tokens <= self.max_tokens:
                    curr_facts.append(fact)
                    curr_tokens += fact_tokens
                else:
                    if curr_facts:
                        table_chunks_text.append("\n".join(curr_facts))
                    curr_facts = [fact]
                    curr_tokens = fact_tokens

            if curr_facts:
                table_chunks_text.append("\n".join(curr_facts))

            # Подклейка хвоста таблицы (< min_tail_tokens)
            if len(table_chunks_text) > 1:
                last_table_tokens = self.token_counter.count_tokens(
                    table_chunks_text[-1]
                )
                if last_table_tokens < self.min_tail_tokens:
                    tail = table_chunks_text.pop()
                    table_chunks_text[-1] = table_chunks_text[-1] + "\n" + tail

            for table_slice in table_chunks_text:
                chunk_id = f"{node.node_id}_c{chunk_idx:02d}"
                tok_count = self.token_counter.count_tokens(table_slice)
                chunks.append(
                    ParsedChunkSchema(
                        chunk_id=chunk_id,
                        node_id=node.node_id,
                        text=table_slice,
                        context_prefix=node.section_path,
                        hyp_questions=[],
                        has_table=True,
                        embedding_model_version="bge-m3",
                        token_count=tok_count,
                    )
                )
                chunk_idx += 1
            return chunks

        # 2. Чанкинг текстового содержимого узла
        text_content = node.full_content.strip()
        if text_content:
            text_slices = self._split_text_to_chunks(text_content)
            for slice_text in text_slices:
                chunk_id = f"{node.node_id}_c{chunk_idx:02d}"
                tok_count = self.token_counter.count_tokens(slice_text)
                chunks.append(
                    ParsedChunkSchema(
                        chunk_id=chunk_id,
                        node_id=node.node_id,
                        text=slice_text,
                        context_prefix=node.section_path,
                        hyp_questions=[],
                        has_table=is_table_node,
                        embedding_model_version="bge-m3",
                        token_count=tok_count,
                    )
                )
                chunk_idx += 1

        return chunks
