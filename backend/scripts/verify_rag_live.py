"""Скрипт сквозной проверки RAG: гибридный поиск Qdrant + удаленный Ollama (Qwen 3.5:2b)."""

import asyncio

from src.rag.schemas import (
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagQueryRequestSchema,
    RagSentenceEventSchema,
    RagSourcesEventSchema,
)
from src.rag.service import RagService


async def main() -> None:
    service = RagService()

    print("=" * 60)
    print("ТЕСТ 1: Релевантный вопрос по регламенту Портала поставщиков")
    print("=" * 60)
    req1 = RagQueryRequestSchema(query="Как подписать протокол разногласий?")
    events1 = []
    async for ev in service.generate_answer(req1):
        events1.append(ev)
        if isinstance(ev, RagSourcesEventSchema):
            print(
                f"-> [SOURCES] Найдено источников в Qdrant: {len(ev.sources)}"
            )
            for s in ev.sources:
                print(
                    f"   * [{s.chunk_id}] {s.title} (score: {s.relevance_score:.4f})"
                )
        elif isinstance(ev, RagSentenceEventSchema):
            status = "ВЕРИФИЦИРОВАНО" if ev.verified else "НЕ ВЕРИФИЦИРОВАНО"
            print(f"-> [SENTENCE {ev.sentence_idx}] [{status}]: {ev.text}")
        elif isinstance(ev, RagDoneEventSchema):
            print(
                f"-> [DONE] Итоговый ответ (all_verified={ev.all_verified}):\n{ev.text}"
            )
        elif isinstance(ev, RagDegradedModeEventSchema):
            print(f"-> [DEGRADED]: {ev.message}")
        else:
            msg = getattr(ev, "message", "")
            print(f"-> [STATUS {ev.event}]: {msg}")

    print("\n" + "=" * 60)
    print(
        "ТЕСТ 2: Нерелевантный вопрос (проверка аварийной деградации ADR 0005)"
    )
    print("=" * 60)
    # Поиск по нерелевантной теме не должен выдавать чанки или вызывать LLM
    # Если Qdrant пуст или нет чанков, отдается degraded_mode
    req2 = RagQueryRequestSchema(
        query="Какой рецепт приготовления плова со специями?"
    )
    degraded_triggered = False
    async for ev in service.generate_answer(req2):
        if isinstance(ev, RagDegradedModeEventSchema):
            degraded_triggered = True
            print(f"-> [УСПЕХ ДЕГРАДАЦИИ]: {ev.message}")
        elif isinstance(ev, RagDoneEventSchema):
            print(f"-> [DONE]: {ev.text}")
        else:
            msg = getattr(ev, "message", "")
            print(f"-> [{ev.event}]: {msg}")

    print("\n" + "=" * 60)
    print("ИТОГИ СКВОЗНОЙ ПРОВЕРКИ:")
    has_sources = any(
        isinstance(e, RagSourcesEventSchema) and len(e.sources) > 0
        for e in events1
    )
    has_done = any(isinstance(e, RagDoneEventSchema) for e in events1)
    print(f"1. Поиск в Qdrant вернул источники: {has_sources}")
    print(f"2. Qwen 3.5 сгенерировал потоковый ответ: {has_done}")
    print(f"3. Режим деградации на нерелевантный запрос: {degraded_triggered}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
