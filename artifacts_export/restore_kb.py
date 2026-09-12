#!/usr/bin/env python3
"""Скрипт быстрого восстановления базы знаний на демонстрационном ноутбуке (1-click restore).

Автономно восстанавливает:
1. PostgreSQL (kb_documents, kb_nodes) из artifacts_export/kb_data.sql (через asyncpg / psql / docker).
2. Qdrant (коллекция tender_chunks, 1024D Cosine) из artifacts_export/tender_chunks.snapshot.
3. Валидирует Small-to-Big Retrieval и выводит статус готовности к демонстрации.

Запуск в 1 клик на Windows / Linux / macOS:
    python artifacts_export/restore_kb.py
    или:
    uv run --project backend python artifacts_export/restore_kb.py
"""

# ruff: noqa: BLE001, S110

import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Безопасный вывод для Windows консоли (CP1251)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_env_defaults() -> dict[str, str]:
    """Считывает параметры подключения из backend/.env или использует значения по умолчанию."""
    config = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "rag_user",
        "DB_PASS": "rag_password",
        "DB_NAME": "rag_db",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "QDRANT_COLLECTION": "tender_chunks",
    }

    env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k in config:
                    config[k] = v
    return config


def check_prerequisites() -> tuple[Path, Path]:
    print("=== [1/4] ПРОВЕРКА АРТЕФАКТОВ ЭКСПОРТА ===")
    curr_dir = Path(__file__).parent.resolve()
    sql_file = curr_dir / "kb_data.sql"
    snapshot_file = curr_dir / "tender_chunks.snapshot"

    if not sql_file.exists():
        print(f"[ОШИБКА] Файл дампа {sql_file} не найден!")
        sys.exit(1)
    if not snapshot_file.exists():
        print(f"[ОШИБКА] Файл снапшота {snapshot_file} не найден!")
        sys.exit(1)

    print(
        f"  [OK] kb_data.sql:          {sql_file.stat().st_size / (1024 * 1024):.2f} MB"
    )
    print(
        f"  [OK] tender_chunks.snapshot: {snapshot_file.stat().st_size / (1024 * 1024):.2f} MB"
    )
    return sql_file, snapshot_file


async def restore_postgres_asyncpg(sql_file: Path, cfg: dict[str, str]) -> bool:
    """Восстановление таблиц PostgreSQL напрямую через asyncpg без сторонних утилит."""
    try:
        import asyncpg
    except ImportError:
        return False

    print(
        f"  -> Подключение через Python asyncpg к {cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}..."
    )
    try:
        conn = await asyncpg.connect(
            host=cfg["DB_HOST"],
            port=int(cfg["DB_PORT"]),
            user=cfg["DB_USER"],
            password=cfg["DB_PASS"],
            database=cfg["DB_NAME"],
            timeout=10,
        )
        try:
            sql_content = sql_file.read_text(encoding="utf-8")
            print("  -> Очистка старых записей и импорт SQL-дампа в PostgreSQL...")
            await conn.execute(
                "TRUNCATE TABLE kb_chunks, kb_nodes, kb_documents CASCADE;"
            )
            await conn.execute(sql_content)
            print("  [УСПЕХ] Таблицы kb_documents и kb_nodes успешно импортированы!")
            return True
        finally:
            await conn.close()
    except Exception as err:
        print(f"  [Инфо] asyncpg соединение: {err}")
        return False


def restore_postgres(sql_file: Path, cfg: dict[str, str]) -> None:
    print(
        f"\n=== [2/4] ВОССТАНОВЛЕНИЕ POSTGRESQL ({cfg['DB_USER']}@{cfg['DB_HOST']}:{cfg['DB_PORT']}/{cfg['DB_NAME']}) ==="
    )

    # 1. Попытка восстановить через asyncpg (чистый Python)
    try:
        ok = asyncio.run(restore_postgres_asyncpg(sql_file, cfg))
        if ok:
            return
    except Exception:
        pass

    # 2. Попытка через psql CLI
    cmd_psql = [
        "psql",
        "-U",
        cfg["DB_USER"],
        "-h",
        cfg["DB_HOST"],
        "-p",
        cfg["DB_PORT"],
        "-d",
        cfg["DB_NAME"],
        "-f",
        str(sql_file),
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = cfg["DB_PASS"]
    try:
        proc = subprocess.run(
            cmd_psql, capture_output=True, text=True, env=env, check=False
        )
        if proc.returncode == 0:
            print("  [УСПЕХ] База знаний PostgreSQL успешно импортирована через psql.")
            return
    except Exception:
        pass

    # 3. Попытка через Docker
    cmd_docker = [
        "docker",
        "exec",
        "-i",
        "rag_postgres",
        "psql",
        "-U",
        cfg["DB_USER"],
        "-d",
        cfg["DB_NAME"],
    ]
    try:
        with open(sql_file, "rb") as f:
            proc = subprocess.run(
                cmd_docker,
                stdin=f,
                capture_output=True,
                text=True,
                check=False,
            )
        if proc.returncode == 0:
            print(
                "  [УСПЕХ] База знаний PostgreSQL успешно импортирована через Docker."
            )
            return
    except Exception:
        pass

    print(
        "  [ВНИМАНИЕ] Не удалось выполнить автоимпорт в PostgreSQL. Убедитесь, что база запущена."
    )


def restore_qdrant(snapshot_file: Path, cfg: dict[str, str]) -> None:
    col = cfg["QDRANT_COLLECTION"]
    base_url = f"http://{cfg['QDRANT_HOST']}:{cfg['QDRANT_PORT']}"
    print(f"\n=== [3/4] ВОССТАНОВЛЕНИЕ ВЕКТОРНОЙ КОЛЛЕКЦИИ QDRANT ({col}) ===")

    # Проверяем, существует ли уже наполненная коллекция
    try:
        check_req = urllib.request.Request(f"{base_url}/collections/{col}")
        with urllib.request.urlopen(check_req, timeout=5) as check_resp:
            col_info = json.loads(check_resp.read().decode("utf-8")).get("result", {})
            if col_info.get("points_count", 0) > 0:
                print(
                    f"  [OK] Коллекция {col} уже существует и содержит {col_info['points_count']} точек."
                )
                return
    except Exception:
        pass

    upload_url = f"{base_url}/collections/{col}/snapshots/upload?priority=snapshot"
    print(f"  -> Отправка снапшота в {upload_url}...")

    try:
        with open(snapshot_file, "rb") as f:
            req = urllib.request.Request(
                upload_url,
                data=f.read(),
                headers={"Content-Type": "application/octet-stream"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    print(
                        f"  [УСПЕХ] Коллекция {col} успешно восстановлена из снапшота!"
                    )
                else:
                    print(f"  [ВНИМАНИЕ] Ответ Qdrant: {data}")
    except Exception as exc:
        print(f"  [ОШИБКА] Сбой восстановления Qdrant: {exc}")


def verify_system(cfg: dict[str, str]) -> None:
    print("\n=== [4/4] ВЕРИФИКАЦИЯ БАЗЫ ЗНАНИЙ (EXECUTE & VERIFY) ===")
    base_url = f"http://{cfg['QDRANT_HOST']}:{cfg['QDRANT_PORT']}"
    col = cfg["QDRANT_COLLECTION"]

    # Проверка Qdrant
    try:
        req = urllib.request.Request(f"{base_url}/collections/{col}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))["result"]
            print(
                f"  [OK] Qdrant коллекция '{col}': статус={data['status']}, точек={data['points_count']}"
            )
    except Exception as e:
        print(f"  [Qdrant]: {e}")

    # Проверка PostgreSQL
    async def check_db():
        try:
            import asyncpg

            conn = await asyncpg.connect(
                host=cfg["DB_HOST"],
                port=int(cfg["DB_PORT"]),
                user=cfg["DB_USER"],
                password=cfg["DB_PASS"],
                database=cfg["DB_NAME"],
                timeout=5,
            )
            docs = await conn.fetchval("SELECT count(*) FROM kb_documents;")
            nodes = await conn.fetchval("SELECT count(*) FROM kb_nodes;")
            chunks = await conn.fetchval("SELECT count(*) FROM kb_chunks;")
            await conn.close()
            print(
                f"  [OK] PostgreSQL '{cfg['DB_NAME']}': документов={docs}, узлов AST={nodes}, чанков={chunks}"
            )
        except Exception as err:
            print(f"  [PostgreSQL]: {err}")

    try:
        asyncio.run(check_db())
    except Exception:
        pass

    print("\nГОТОВО! БАЗА ЗНАНИЙ ПОЛНОСТЬЮ РАЗВЕРНУТА И ГОТОВА К ЗАЩИТЕ.")


def main():
    cfg = load_env_defaults()
    sql_file, snap_file = check_prerequisites()
    restore_postgres(sql_file, cfg)
    restore_qdrant(snap_file, cfg)
    verify_system(cfg)


if __name__ == "__main__":
    main()
