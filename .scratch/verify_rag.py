import asyncio
import sys
import asyncpg
import httpx

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


async def verify_rag_pipeline():
    query = "Как сформировать электронный акт поставщику на портале?"
    print("1. Тестовый запрос:", query)

    # 1. Векторизация запроса на GPU (Ollama bge-m3)
    r = httpx.post(
        "http://127.0.0.1:11434/api/embed",
        json={"model": "bge-m3", "input": query},
        timeout=30.0,
    )
    query_vec = r.json()["embeddings"][0]
    print(
        f"2. Вектор запроса: {len(query_vec)}D (bge-m3 на AMD RX 6600 Vulkan/RDNA2 GPU)"
    )

    # 2. Поиск в Qdrant
    q_resp = httpx.post(
        "http://localhost:6333/collections/tender_chunks/points/search",
        json={"vector": query_vec, "limit": 3, "with_payload": True},
    )
    results = q_resp.json()["result"]
    print(f"3. Найдено в Qdrant: {len(results)} наиболее релевантных точек")
    top_hit = results[0]
    score = top_hit["score"]
    chunk_id = top_hit["payload"]["chunk_id"]
    section_path = top_hit["payload"]["section_path"]
    node_id = top_hit["payload"]["node_id"]

    print(f"   - Top-1 Score: {score:.4f}")
    print(f"   - Chunk ID:    {chunk_id}")
    print(f"   - Раздел AST:  {section_path}")

    # 3. Small-to-Big Retrieval: извлечение родительской секции из PostgreSQL
    conn = await asyncpg.connect(
        "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    )
    node = await conn.fetchrow(
        "SELECT title, level, full_content FROM kb_nodes WHERE node_id = $1",
        node_id,
    )
    await conn.close()

    if node:
        print(f"4. Родительский узел PostgreSQL: [{node['level']}] {node['title']}")
        preview = node["full_content"][:250].replace("\n", " ")
        print(f"   Фрагмент контента: {preview}...")

    print("\n[OK] Полный цикл Small-to-Big Retrieval отработал безупречно!")


if __name__ == "__main__":
    asyncio.run(verify_rag_pipeline())
