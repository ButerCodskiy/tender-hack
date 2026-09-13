"""Системные промпты и шаблоны контекста RAG-генератора."""

import re

from src.rag.schemas import ContextChunk

RAG_SYSTEM_PROMPT = """\
Ты — интеллектуальный эксперт-консультант службы поддержки Портала поставщиков Москвы и регламентов государственных и коммерческих закупок (44-ФЗ, 223-ФЗ).

Твоя цель — предоставить точный, юридически и технически выверенный ответ на вопрос пользователя строго на основе переданных нормативных документов.

КРИТИЧЕСКИЕ ПРАВИЛА:
1. ИСТОЧНИКИ И СНОСКИ:
   - Отвечай исключительно на основе предоставленных нормативных источников ([Источник N | ...]).
   - Подтверждай каждое нормативное требование, порядок действий, срок, процент или сумму сноской вида [^N], где N — порядковый номер источника из переданного списка (например: [^1], [^2]).
   - Запрещено указывать сноски на номера источников, которые отсутствуют в переданном списке.

2. СТРОГИЙ ЗАПРЕТ ВЫМЫСЛА (DEFLECTION RULE):
   - Если в предоставленных фрагментах нормативной базы НЕТ информации для полного или точного ответа на вопрос пользователя, прямо и четко заяви: «В предоставленных регламентах и нормативных документах информация по вашему вопросу отсутствует. Рекомендуем обратиться к оператору технической поддержки или уточнить запрос.»
   - Категорически запрещено выдумывать статьи законов, пункты регламентов, сроки, формулировки или технические процедуры, если их нет в переданном контексте.

3. СТИЛЬ И ФОРМАТИРОВАНИЕ:
   - Деловой, нейтральный и лаконичный тон.
   - Используй форматирование Markdown (списки, абзацы). Не сплошным текстом.
   - Избегай общих вводных фраз без конкретики («Как известно», «В современном мире»).

4. СТРОГИЙ ЗАПРЕТ ФОРМАТА JSON:
   - Отвечай исключительно естественным языком с Markdown-разметкой.
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО оборачивать ответ в JSON, выводить поля вида {"query": ..., "answer": ..., "next_steps": ...} или программный код.
   - Ответ должен сразу начинаться с текста сообщения пользователю.
"""


def sanitize_history_text(text: str) -> str:
    """Очищает реплику диалога от системных дисклеймеров и следов JSON."""
    cleaned = re.sub(
        r"\[Данные о сроках, суммах или статьях не подтверждены регламентом Портала и скрыты\.[^\]]*\]\s*",
        "",
        text,
    )
    if '"next_steps"' in cleaned or '"answer"' in cleaned:
        ans_match = re.search(r'"answer"\s*:\s*"([^"]+)"', cleaned)
        if ans_match:
            cleaned = ans_match.group(1).replace("\\n", "\n")
        else:
            cleaned = re.sub(r'["\{\}\]]+', "", cleaned).strip()
    return cleaned.strip()


def format_context_chunk(idx: int, chunk: ContextChunk) -> str:
    """Форматирует отдельный чанк нормативного контекста для промпта."""
    section_path = chunk.section_path or "Общий раздел"
    title = chunk.title or f"Документ {chunk.doc_id}"
    body = (chunk.quote_text or "").strip()

    return f"[Источник {idx} | {section_path} | {title}]\n{body}"


def format_rag_prompt(
    query: str,
    chunks: list[ContextChunk],
    conversation_history: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    """Формирует системный и пользовательский промпт для генерации ответа.

    Args:
        query: Текст вопроса пользователя.
        chunks: Список найденных нормативных фрагментов базы знаний.
        conversation_history: История реплик диалога (роль и текст).

    Returns:
        Кортеж из (системный промпт, пользовательский промпт с контекстом).
    """
    context_parts: list[str] = []
    if chunks:
        context_parts.append("Найденные нормативные регламенты и статьи:")
        for idx, chunk in enumerate(chunks, start=1):
            context_parts.append(format_context_chunk(idx, chunk))
    else:
        context_parts.append(
            "Нормативные регламенты по данному запросу не найдены."
        )

    formatted_context = "\n\n".join(context_parts)

    user_parts: list[str] = [formatted_context]

    if conversation_history:
        history_lines: list[str] = ["История предыдущего диалога:"]
        for msg in conversation_history[
            -6:
        ]:  # Ограничиваем окно последних реплик
            role = "Пользователь" if msg.get("role") == "user" else "Ассистент"
            raw_text = msg.get("text", "")
            text = sanitize_history_text(raw_text)
            if text:
                history_lines.append(f"{role}: {text}")
        if len(history_lines) > 1:
            user_parts.append("\n".join(history_lines))

    user_parts.append(
        f"Вопрос пользователя:\n{query.strip()}\n\n"
        "Ответ ассистента-консультанта (отвечай строго связным текстом с Markdown-списками без JSON, без фигурных скобок и без технических полей):"
    )

    user_prompt = "\n\n---\n\n".join(user_parts)
    return RAG_SYSTEM_PROMPT, user_prompt
