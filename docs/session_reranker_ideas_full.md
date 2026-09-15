# Архив диалога и идей: Рефакторинг математики реранкера и RAG

**ID сессии:** `6533c9d8-ca7c-4fb6-8f77-e5c3af926685`

## 📋 Утверждённый план реализации (Implementation Plan)

# План реализации: Рефакторинг математики реранкера, динамического порога Cross-Encoder и агрегации родительских статей в RAG

## Описание задачи
Полная замена математики гибридного реранжирования и интеграции Cross-Encoder в RAG-пайплайне (`backend/src/rag/`):
1. Переход от некорректного линейного сложения разнородных скоров ($0.65 \cdot S_{\text{dense}} + 0.35 \cdot S_{\text{lex}}$) к **Weighted Reciprocal Rank Fusion (Weighted RRF, $k=60$)** для нормализации независимых распределений первичного поиска.
2. Внедрение **динамического адаптивного порога отсечения Cross-Encoder** $T(q) = \text{clamp}(T_{\text{floor}} + \beta \cdot (|q| - L_{\text{min}}), \; T_{\text{floor}}, \; T_{\text{ceil}})$ с защитой коротких запросов (floor $0.28$) и безусловным bypass для кодов ошибок (`0x...`) и нормативных статей (`ст. 93 44-ФЗ`).
3. **Агрегация и дедупликация дочерних чанков в родительские статьи**: переход от россыпи 9 мелких фрагментов к $4$–$5$ целостным родительским статьям (`node_id`) по формуле:
   $$S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln\left(1 + \sum_{i \in \text{other}} S_i\right)$$
4. **Нейтрализация эффекта «Lost in the Middle»**: U-образная перестановка отобранных статей $[1, 3, 5, 4, 2]$, размещающая наиболее релевантные статьи на границах контекстного окна LLM.

---

## User Review Required

> [!IMPORTANT]
> - Изменение сигнатур/поведения `rerank(...)`: реранкер теперь возвращает не просто отсортированные дочерние чанки, а полноценно агрегированные и дедуплицированные родительские узлы (4–5 статей) с сохранением дочерних цитат и перестановкой Lost-in-the-Middle.
> - Тесты в `backend/tests/rag/` (в частности, `test_reranker_hybrid.py` и `test_rag_pipeline_hardening.py`), проверявшие старую формулу линейного сложения $0.60 \cdot S_{\text{dense}} + 0.40 \cdot R_{\text{lex}}$, будут обновлены на проверку инвариантов RRF, динамического порога и родительской агрегации.

---

## Предлагаемые изменения

### 1. Подсистема RAG: Математика реранжирования и Cross-Encoder

#### [MODIFY] [backend/src/rag/reranker.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/reranker.py)
- Реализовать функцию/метод `compute_weighted_rrf(dense_ranks, lexical_ranks, k=60, w_dense=0.65, w_lex=0.35)`.
- Реализовать функцию/метод `calculate_dynamic_threshold(query)` с floor $0.28$, ceiling $0.55$, коэффициентом наклона $\beta=0.015$ и bypass для `0x...` и статей законов.
- Реализовать метод `aggregate_parent_articles(chunks, max_parents=5)`: группировка по `node_id`, вычисление $S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln(1 + \sum S_{\text{other}})$.
- Реализовать `reorder_lost_in_middle(items)`: краевая U-образная раскладка $[1, 3, 5, 4, 2]$.
- Модернизировать `TransformerCrossEncoderReranker`:
  - Применение попарного скоринга к Top-15 кандидатам из RRF.
  - Фильтрация по динамическому порогу $T(q)$.
  - Агрегация и перестановка Lost-in-the-Middle перед возвратом.
  - Сохранение плавного фолбэка на лексико-плотный RRF при отсутствии GPU/модели.

---

### 2. Подсистема RAG: Расширение первичного поиска (High Recall)

#### [MODIFY] [backend/src/rag/retriever.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/retriever.py)
- Увеличить глубину первичного сбора кандидатов: `top_k=30` для dense и `top_k=30` для sparse/lexical, чтобы гарантировать Recall@30 $\ge 0.95$.
- Передавать в реранкер ранги dense и lexical (или параллельный RRF-список).
- Сохранить механизм Small-to-Big гидратации из PostgreSQL (`kb_nodes`), передавая полные тексты родительских статей в агрегатор.

---

### 3. Фасадный сервис диалогов RAG

#### [MODIFY] [backend/src/rag/service.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/service.py)
- Связать 2-этапный конвейер:
  1. `Retriever.retrieve()`: широкий сбор Top-30 кандидатов.
  2. `Reranker.rerank()`: Weighted RRF -> Top-15 Cross-Encoder -> фильтрация по динамическому порогу -> схлопывание в 4–5 родительских статей -> Lost-in-the-Middle.
- Отправка в SSE-событие `RagSourcesEventSchema` агрегированных родительских статей вместо 9 сырых фрагментов.

---

### 4. Тестовый комплекс

#### [MODIFY] [backend/tests/rag/test_reranker_hybrid.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/tests/rag/test_reranker_hybrid.py)
- Обновить тесты с проверки старой линейной формулы на Weighted RRF, свойства ранговой инвариантности, приоритет hex-ошибок и статей законов.
- Добавить тесты на динамический порог: короткие запросы (floor 0.28), длинные запросы (> 0.40), bypass hex-кодов `0x...` и `ст. 93 44-ФЗ`.
- Добавить тесты на агрегацию нескольких дочерних чанков в одну родительскую статью и U-образный порядок Lost-in-the-Middle.

#### [MODIFY] [backend/tests/rag/test_rag_pipeline_hardening.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/tests/rag/test_rag_pipeline_hardening.py)
- Адаптировать проверки реранкера под RRF и динамический порог.

---

## План верификации

### Автоматические тесты
1. Запуск тестового набора реранкера и RAG-пайплайна:
   ```powershell
   backend\.venv\Scripts\pytest backend\tests\rag\test_reranker_hybrid.py -v
   backend\.venv\Scripts\pytest backend\tests\rag\test_rag_pipeline_hardening.py -v
   backend\.venv\Scripts\pytest backend\tests\rag\test_rag_service.py -v
   ```
2. Линтинг и форматирование кода:
   ```powershell
   backend\.venv\Scripts\ruff check backend\src\rag\reranker.py backend\src\rag\retriever.py backend\src\rag\service.py
   ```

### Ручная проверка сквозного сценария
1. Прогон `python scripts/ast_skeleton.py backend/src/rag/reranker.py` для контроля чистоты интерфейсов и аннотаций.
2. Тестовый вызов `RagService.generate_answer` со сложным многословным запросом и коротким запросом (с hex-ошибкой `0x80070005`) для проверки генерации SSE-событий с 4–5 уникальными источниками.


---

## 🚀 Результаты и формулы (Walkthrough)

# Результаты переработки математики реранкера и логики Cross-Encoder

В соответствии с утвержденным [ADR_RERANKER.md](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/docs/adr/ADR_RERANKER.md) и планом реализации полностью переписан пайплайн реранжирования и интеграции Cross-Encoder в RAG-модуле (`backend/src/rag/`).

---

## 1. Внедренные математические компоненты

### 1.1 Weighted Reciprocal Rank Fusion (Weighted RRF, $k=60$)
Вместо некорректного линейного сложения разнородных распределений dense и lexical скоров реализована формула:

$$RRF(d) = \frac{0.65}{60 + \text{rank}_{\text{dense}}(d)} + \frac{0.35}{60 + \text{rank}_{\text{lexical}}(d)}$$

- Dense-канал обеспечивает семантическую полноту поиска.
- Lexical-канал сохраняет терминологическую точность.
- Сохранена логика точного буста (+0.40 за hex-ошибки `0x...`, +0.30 за номера статей законов `ст. 93 44-ФЗ` и `pin_to_top` при совпадении в заголовке).

### 1.2 Динамический адаптивный порог отсечения Cross-Encoder ($T(q)$)
Реализована функция адаптивного отсечения по формуле:

$$T(q) = \text{clamp}(0.28 + 0.015 \cdot \max(0, |q| - 3), 0.28, 0.55)$$

- При длине запроса $\le 3$ слов порог равен базовому полу $0.28$.
- При росте длины запроса порог плавно возрастает вплоть до потолка $0.55$.
- **Bypass-механизм**: при обнаружении шестнадцатеричных кодов ошибок (`0x...`) или номеров статей регламентов/законов (`ст. 93 44-ФЗ`) порог отключается ($T=0$), гарантируя пропуск критических совпадений.

### 1.3 Калибровка логитов Cross-Encoder
В классе `TransformerCrossEncoderReranker`:
- Модель `BAAI/bge-reranker-base` оценивает пары `(query, document)`.
- Для инвариантности к сырым отрицательным значениям логитов модели (особенно на русскоязычном домене) применена внутрибатчевая Min-Max калибровка с лексическим анкором:

$$S_{\text{final}} = 0.65 \cdot S_{\text{neural}} + 0.35 \cdot S_{\text{lexical}} + \text{boost}$$

- Если все кандидаты опускаются ниже динамического порога $T(q)$, выдача безопасно пустеет, что переводит `RagService` в `degraded_mode` (защита от галлюцинаций LLM согласно ADR-0005).

### 1.4 Агрегация дочерних чанков в родительские статьи
Вместо фрагментарной россыпи мелких абзацев кандидаты группируются по `node_id` (или родительской секции) с кумулятивным насыщением по формуле:

$$S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln\left(1 + \sum S_{\text{other}}\right)$$

- Выдача ограничивается 4–5 уникальными родительскими статьями (`max_parents=5`).
- Статьи с несколькими релевантными подпунктами получают обоснованный кумулятивный бонус.

### 1.5 Нейтрализация эффекта «Lost in the Middle»
Отобранные статьи реорганизуются по U-образной схеме:

$$\text{Индексы ранга} \longrightarrow [1, 3, 5, 4, 2]$$

- Наиболее релевантные первоисточники (1 и 2) размещаются по краям контекстного окна, где внимание модели максимально (начало и конец промпта).

---

## 2. Модифицированные файлы

| Файл | Изменения |
|---|---|
| [`schemas.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/schemas.py) | В модель [RagSourceChunkSchema](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/schemas.py#L60) добавлено поле `node_id: str \| None = None`. |
| [`retriever.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/retriever.py) | Увеличен `top_k=30` для максимизации первичного recall; убрана преждевременная дедупликация родительских секций, сохранена передача `node_id` в чанки для реранкера. |
| [`reranker.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/reranker.py) | Реализованы `compute_weighted_rrf`, `calculate_dynamic_threshold`, `aggregate_parent_articles`, `reorder_lost_in_middle`; обновлены [LexicalDenseReranker](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/reranker.py#L170) и [TransformerCrossEncoderReranker](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/reranker.py#L350). |
| [`service.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/service.py) | Переранжирование вызывается с параметром `max_parents=5`; при пустой отфильтрованной выдаче осуществляется безопасный переход в `degraded_mode`. |
| [`test_reranker_hybrid.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/tests/rag/test_reranker_hybrid.py) | Добавлены тесты RRF, динамического порога, агрегации родителей, U-перестановки. |
| [`test_rag_pipeline_hardening.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/tests/rag/test_rag_pipeline_hardening.py) | Актуализированы тесты ранжирования под Weighted RRF. |
| [`test_rag_service.py`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/tests/rag/test_rag_service.py) | Синхронизирована структура событий (статус `generating`) и запросы под мок-источники. |
| [`docs/adr/ADR_RERANKER.md`](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/docs/adr/ADR_RERANKER.md) | Архитектурное решение с матрицей компромиссов и формулами зафиксировано в репозитории. |

---

## 3. Результаты верификации

### Юнит-тесты (pytest)
- **`backend/tests/rag/test_reranker_hybrid.py`**: **8/8 PASSED** (100%)
- **`backend/tests/rag/test_rag_pipeline_hardening.py`**: **9/9 PASSED** (100%)
- **`backend/tests/rag/test_rag_service.py`**: **5/5 PASSED** (100%)
- **`backend/tests/rag/test_rag_retriever.py`**: **3/3 PASSED** (100%)
- **Итого**: **25/25 тестов пройдены успешно**.

### Статический анализ кода (ruff)
```bash
ruff check backend/src/rag/reranker.py backend/src/rag/retriever.py backend/src/rag/schemas.py backend/src/rag/service.py backend/tests/rag/
```
Результат: **All checks passed!**


---

## 💬 Полный протокол обсуждения (Диалог)

### 👤 Пользователь (Сообщение 1)

Напиши Python-скрипт scripts/ast_skeleton.py. Он должен принимать путь к файлу через sys.argv, парсить его синтаксическое дерево через встроенный модуль ast и возвращать исходный код, в котором тела всех функций и методов (node.body) заменены на ... (ast.Ellipsis). Должны остаться только импорты, объявления классов, сигнатуры методов с type hints и докстринги. Выведи только полностью рабочий код скрипта.


<USER_SETTINGS_CHANGE>
The user changed setting `Model Selection` from None to Gemini 3.8 Flash (High). No need to comment on this change if the user doesn't ask about it. If reporting what model you are, please use a human readable name instead of the exact string.
</USER_SETTINGS_CHANGE>

### 🤖 Ассистент

```python
import ast
import contextlib
import io
from pathlib import Path
import sys


def is_docstring(stmt: ast.AST) -> bool:
    """Проверяет, является ли узел синтаксического дерева строковой константой (докстрингом)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


class SkeletonTransformer(ast.NodeTransformer):
    """Трансформер AST, сохраняющий только импорты, объявления классов,

    сигнатуры функций/методов с type hints и докстринги.
    Тела всех функций и методов заменяются на ast.Ellipsis (...).
    """

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: list[ast.stmt] = []
        if node.body and is_docstring(node.body[0]):
            new_body.append(node.body[0])
            stmts = node.body[1:]
        else:
            stmts = node.body

        for stmt in stmts:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                new_body.append(stmt)
            elif isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                transformed = self.visit(stmt)
                if transformed is not None:
                    new_body.append(transformed)

        node.body = new_body
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        new_body: list[ast.stmt] = []
        if node.body and is_docstring(node.body[0]):
            new_body.append(node.body[0])
            stmts = node.body[1:]
        else:
            stmts = node.body

        for stmt in stmts:
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                transformed = self.visit(stmt)
                if transformed is not None:
                    new_body.append(transformed)

        if not new_body:
            new_body = [ast.Expr(value=ast.Constant(value=Ellipsis))]

        node.body = new_body
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._transform_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._transform_function(node)

    def _transform_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        ellipsis_expr = ast.Expr(value=ast.Constant(value=Ellipsis))
        if node.body and is_docstring(node.body[0]):
            node.body = [node.body[0], ellipsis_expr]
        else:
            node.body = [ellipsis_expr]
        return node


def extract_skeleton(source_code: str, filename: str = "<string>") -> str:
    """Парсит синтаксическое дерево и возвращает скелет исходного кода."""
    tree = ast.parse(source_code, filename=filename)
    transformer = SkeletonTransformer()
    transformed_tree = transformer.visit(tree)
    ast.fix_missing_locations(transformed_tree)
    return ast.unparse(transformed_tree)


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        with contextlib.suppress(AttributeError, io.UnsupportedOperation):
            sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        print("Использование: python scripts/ast_skeleton.py <путь_к_файлу>", file=sys.stderr)
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.is_file():
        print(f"Ошибка: файл не найден: {file_path}", file=sys.stderr)
        sys.exit(1)

    source_code = file_path.read_text(encoding="utf-8")
    skeleton = extract_skeleton(source_code, filename=str(file_path))
    print(skeleton)


if __name__ == "__main__":
    main()
```

### 👤 Пользователь (Сообщение 2)

да твой код не работает, я так и не получу ast gitos - PS C:\Users\Дмитрий\OneDrive\Рабочий стол\gitos> & C:/Users/Дмитрий/AppData/Local/Programs/Python/Python312/python.exe "c:/Users/Дмитрий/OneDrive/Рабочий стол/gitos/scripts/ast_skeleton.py"
Использование: python scripts/ast_skeleton.py <путь_к_файлу>
PS C:\Users\Дмитрий\OneDrive\Рабочий стол\gitos> & C:/Users/Дмитрий/AppData/Local/Programs/Python/Python312/python.exe "c:/Users/Дмитрий/OneDrive/Рабочий стол/gitos/scripts/ast_skeleton.py"
Использование: python scripts/ast_skeleton.py <путь_к_файлу>
PS C:\Users\Дмитрий\OneDrive\Рабочий стол\gitos> & C:/Users/Дмитрий/AppData/Local/Programs/Python/Python312/python.exe "scripts/ast_skeleton.py" "service.py"
Ошибка: файл не найден: service.py
PS C:\Users\Дмитрий\OneDrive\Рабочий стол\gitos> & C:/Users/Дмитрий/AppData/Local/Programs/Python/Python312/python.exe "scripts/ast_skeleton.py" .
Ошибка: файл не найден: .
PS C:\Users\Дмитрий\OneDrive\Рабочий стол\gitos>

### 🤖 Ассистент

Скрипт обновлен в [scripts/ast_skeleton.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/scripts/ast_skeleton.py).

### Что было исправлено:
1. **Поддержка директорий**: теперь можно передавать `.` или путь к любой папке (например, `backend/src/chat`). Скрипт рекурсивно находит все `.py` файлы, игнорируя служебные каталоги (`.venv`, `.git`, `__pycache__`, `.pytest_cache` и др.).
2. **Умный поиск по имени файла**: если передать просто имя файла вроде `service.py`, скрипт найдет все соответствующие файлы в подпапках репозитория (`backend/src/chat/service.py`, `backend/src/rag/service.py` и т.д.).
3. **Запуск по умолчанию**: если аргументы не переданы, скрипт автоматически берет текущую директорию (`.`).

---

### Примеры запуска

* **Для конкретного файла (без лишних заголовков)**:
  ```powershell
  python scripts/ast_skeleton.py backend/src/chat/service.py
  ```

* **Поиск файла по имени во всем проекте**:
  ```powershell
  python scripts/ast_skeleton.py service.py
  ```

* **Для определенной директории**:
  ```powershell
  python scripts/ast_skeleton.py backend/src/chat
  ```

* **Для всего репозитория**:
  ```powershell
  python scripts/ast_skeleton.py .
  ```

---

### Полный код [scripts/ast_skeleton.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/scripts/ast_skeleton.py)

```python
import ast
import contextlib
import io
import sys
from pathlib import Path

EXCLUDED_DIRS = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".scratch",
  
<truncated 3225 bytes>
_tree)
    return ast.unparse(transformed_tree)


def should_skip(path: Path) -> bool:
    """Проверяет, находится ли путь в исключаемых служебных директориях."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def find_files(target: Path) -> list[Path]:
    """Находит Python-файлы: по файлу, директории или поиску по имени файла."""
    if target.is_file():
        return [target]

    if target.is_dir():
        return [path for path in target.rglob("*.py") if not should_skip(path)]

    # Если путь не найден напрямую (например, передан service.py без пути)
    return [path for path in Path.cwd().rglob(target.name) if not should_skip(path)]


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        with contextlib.suppress(AttributeError, io.UnsupportedOperation):
            sys.stdout.reconfigure(encoding="utf-8")

    raw_target = sys.argv[1] if len(sys.argv) > 1 else "."
    target = Path(raw_target)

    files = find_files(target)

    if not files:
        print(f"Ошибка: Python-файлы не найдены для: {target}", file=sys.stderr)
        sys.exit(1)

    sorted_files = sorted(files)
    is_multi = len(sorted_files) > 1 or target.is_dir()

    for file_path in sorted_files:
        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = file_path

        if is_multi:
            print(f"\n{'=' * 80}")
            print(f"FILE: {rel_path}")
            print(f"{'=' * 80}\n")

        try:
            source_code = file_path.read_text(encoding="utf-8")
            skeleton = extract_skeleton(source_code, filename=str(file_path))
            print(skeleton)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"[ОШИБКА в {rel_path}] {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

### 👤 Пользователь (Сообщение 3)

@[c:\Users\Дмитрий\OneDrive\Рабочий стол\gitos\scripts\ast_of_project.md] Вот AST-скелет исследуемого модуля. Проанализируй этот архитектурный интерфейс без опоры на старые спецификации. Кратко перечисли по факту: какие DTO или типы модуль принимает на вход, что возвращает и какие внешние зависимости использует. Запрещено придумывать исполнительную логику, которая скрыта за многоточиями. Расска про этот проект подробнее

### 🤖 Ассистент

На основе представленного AST-скелета и объявленных в кодовой базе интерфейсов (строго по сигнатурам методов, типам аннотаций, DTO и докстрингам, **без домысливания скрытой за `...` логики**) проведен детальный анализ архитектуры.

> [!NOTE]
> В переданном файле [scripts/ast_of_project.md](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/scripts/ast_of_project.md) из-за прокрутки консоли зафиксировались интерфейсы тестовых контрактов и ключевых модулей (`operators`, `rag`, `parser`, `unit`). Ниже представлен строгий фактологический разбор интерфейсов ядра системы.

---

### 1. Фактический анализ архитектурных интерфейсов

#### А. Подсистема операторов и очередей (`OperatorService`, `operators`)
* **Входные DTO и типы:**
  - Идентификаторы: `user_id: UUID`, `ticket_id: UUID`, `operator_id: UUID`.
  - Маршрутизация и статусы: `shift_status: str`, `target_line_code: str` (например, `'L1'`, `'L2'`), `transfer_comment: str | None`.
  - Сообщения: `text: str`.
  - Инфраструктура: `now: datetime | None`, `request: Request` (FastAPI).
* **Возвращаемые DTO и типы:**
  - `OperatorProfileResponseSchema` — профиль и смена оператора.
  - `list[OperatorSidebarTicketSchema]` — список закрепленных за оператором обращений.
  - `OperatorTicketWorkspaceSchema` — полное рабочее место оператора с карточкой тикета.
  - `MessageResponseSchema` — результат отправки сообщения.
  - `
<truncated 6290 bytes>
енты, даты и финансовые суммы валидируются со сносками к нормативным источникам. Неподтвержденные факты маскируются защитным дисклеймером (`UNVERIFIED_FACTS_DISCLAIMER`).
   - Поддерживается потоковая генерация Server-Sent Events (SSE) с разбивкой предложений через `razdel` и детерминированный откат в `degraded_mode` без падения сервиса.

3. **Рабочее место оператора с AI Copilot:**
   - Фоновая задача `generate_copilot_summary` формирует краткую выжимку проблемы из истории переписки и подтягивает исторические прецеденты из векторной коллекции похожих закрытых обращений.
   - Поддерживается бесшовный фолбэк на локальный инференс (Ollama) с жесткими лимитами по таймаутам.

4. **Отказоустойчивость очередей и контроль SLA (High Availability):**
   - Оперативная буферизация в **Redis**: очереди линий поддержки `queue:line:{code}` с приоритетом (**P0** в голову очереди `LPUSH`, **P1/P2** в хвост `RPUSH`).
   - Фоновый планировщик таймаутов (`check_timeouts`): выявление брошенных клиентами тикетов, контроль обрыва связи операторов (10 минут), автоматический перевод в `offline` и возврат тикетов в очередь.
   - Механизм самовосстановления (`recover_queued_tickets_from_db`): атомарный pipeline (DEL + RPUSH) под распределенным замком (`MockDistributedLock` / Redis-lock).

### 👤 Пользователь (Сообщение 4)

/ask-matt /grill-with-docs /grill-me Задача: Полностью переписать математику реранкера и логику кросс-энкодера для RAG.Контекст и проблемы:Текущий реранкер работает математически неверно: он просто складывает лексический и семантический скор с коэффициентами, игнорируя распределения. Нужно перевести логику на учет рангов внутри их распределений (например, Reciprocal Rank Fusion или аналоги).Кросс-энкодер некорректно работает с порогом (сейчас он используется как BI-энкодер, что бестолково).Нужно максимизировать recall для первичного поиска, а затем использовать кросс-энкодер с динамическим порогом (например, в зависимости от длины запроса).Итоговая выдача должна ограничиваться 4-5 родительскими чанками (полноценными статьями), а не 9 мелкими, с обязательной дедупликацией.Твои действия (выполнять строго по шагам):Интервью (Decision Tree): Задай мне узкие архитектурные вопросы по пограничным состояниям (что делать, если длины запроса не хватает для расчета порога, как дедуплицировать статьи).  Создание ADR: Сгенерируй документ ADR_RERANKER.md. Опиши минимум 3 архитектурные альтернативы математики реранжирования и расчета динамического по
<truncated 682 bytes>
матику в scratch/.

### 🤖 Ассистент

Все этапы выполнены строго по регламенту без изменения боевых файлов проекта.

---

### 1. Результаты архитектурного интервью (Decision Tree)

По итогам серии вопросов согласованы следующие архитектурные решения:
1. **Динамический порог Cross-Encoder**:
   - Формула: $T(q) = \text{clamp}(T_{\text{floor}} + \beta \cdot (|q| - L_{\text{min}}), \; T_{\text{floor}}, \; T_{\text{ceil}})$, где $T_{\text{floor}} = 0.28$, $T_{\text{ceil}} = 0.55$, $\beta = 0.015$, $L_{\text{min}} = 3$.
   - Безусловный **Bypass** базовым порогом ($0.28$) для паттернов системных hex-ошибок (`0x...`) и прямых ссылок на статьи законов (`ст. 93 44-ФЗ`).
2. **Конвейер RAG**: 
   - **Этап 1 (High Recall)**: широкий первичный сбор Top-30 dense + Top-30 sparse/lexical, объединяемый через **Weighted Reciprocal Rank Fusion (Weighted RRF, $k=60$)**.
   - **Этап 2 (Precision Re-rank)**: Top-15 кандидатов передаются в Cross-Encoder с динамическим порогом $T(q)$.
3. **Агрегация и дедупликация родительских статей**:
   - Маппинг дочерних чанков к родителям по `node_id`.
   - Формула скора родительской статьи:
     $$S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln\left(1 + \sum_{i \in \text{other}} S_i\right)$$
   - Ограничение итоговой выдачи $4$–$5$ уникальными родительскими статьями.
4. **Защита от «Lost in the Middle»**:
   - Переупорядочивание итоговых статей по U-образной схеме: $[1, 3, 5, 4, 2]$ (сильнейшие статьи располагаются на граница
<truncated 2950 bytes>
запрос ('подробный регламент обжалования...'): порог = 0.445, bypass = False
  --> УСПЕШНО: Динамический расчет порога ведет себя строго по ТЗ.

[Тест 3] Агрегация чанков в родительские статьи и дедупликация
  Входных дочерних чанков: 6
  Итоговых уникальных родительских статей: 3
    - ART_93 (score=1.0): совпало 3 чанков
    - ART_34 (score=0.8354): совпало 2 чанков
    - SEC_4 (score=0.65): совпало 1 чанков
  --> УСПЕШНО: Дедупликация и кумулятивный скор родителя работают корректно.

[Тест 4] Переупорядочивание Lost in the Middle
  Исходный ранжированный список: ['Article_1', 'Article_2', 'Article_3', 'Article_4', 'Article_5']
  Размещение для промпта LLM:   ['Article_1', 'Article_3', 'Article_5', 'Article_4', 'Article_2']
  --> УСПЕШНО: Лучшие статьи гарантированно размещены в начале и в конце окна внимания.

================================================================================
ВСЕ 4 ВЕРИФИКАЦИОННЫХ ТЕСТА ПРОЙДЕНЫ УСПЕШНО.
================================================================================
```

---

### 4. Статус ограничений (Negative Constraints)

* Боевые файлы проекта в `backend/src/` и `backend/tests/` **не изменялись**.
* Математика полностью изолирована и протестирована в [scratch/reranker_math.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/scratch/reranker_math.py).
* Готовы перейти к переносу в продакшн-код после вашего подтверждения.

### 👤 Пользователь (Сообщение 5)

твоя задача составить план реализации этой таски и идти по нему последовательно, можешь спрашвиать меня предварительно перед составлением плана /grill-me план пройдет мое согласование или праки и мы приступим

### 🤖 Ассистент

План реализации подготовлен в артефакте [implementation_plan.md](file:///C:/Users/Дмитрий/.gemini/antigravity-ide/brain/6533c9d8-ca7c-4fb6-8f77-e5c3af926685/implementation_plan.md).

### Ключевые этапы плана:
1. **[backend/src/rag/reranker.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/reranker.py)**:
   - Внедрение **Weighted RRF ($k=60$)** взамен линейного сложения скоров.
   - Реализация динамического порога отсечения Cross-Encoder (Floor $0.28$, Ceiling $0.55$, наклон $\beta=0.015$, Bypass для кодов ошибок `0x...` и статей законов).
   - Агрегация дочерних чанков в родительские статьи ($S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln(1 + \sum S_{\text{other}})$) и ограничение 4–5 уникальными статьями.
   - U-образное переупорядочивание для нейтрализации эффекта «Lost in the Middle» ($[1, 3, 5, 4, 2]$).
2. **[backend/src/rag/retriever.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/retriever.py)**:
   - Расширение первичного сбора кандидатов (`top_k=30` dense + `top_k=30` sparse) для максимизации Recall@30.
3. **[backend/src/rag/service.py](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/service.py)**:
   - Подключение нового 2-этапного конвейера и передача в SSE-события 4–5 агрегированных родительских статей вместо 9 сырых фрагментов.
4. **Тесты**:
   - Обновление и расширение тестовых наборов `test_reranker_hybrid.py` и `test_rag_pipeline_hardening.py`.

Ознакомьтесь с планом. Если есть замечания или уточнения — внесу правки. Если план утвержден — подтвердите, и я приступлю к реализации.

### 👤 Пользователь (Сообщение 6)

Comments on artifact URI: file:///c%3A/Users/%D0%94%D0%BC%D0%B8%D1%82%D1%80%D0%B8%D0%B9/.gemini/antigravity-ide/brain/6533c9d8-ca7c-4fb6-8f77-e5c3af926685/implementation_plan.md

The user has approved this document.

### 🤖 Ассистент

Запущен прогон тестов `backend/tests/rag/test_reranker_hybrid.py`. Ожидаю завершения для анализа результатов.

### 🤖 Ассистент

Запущен прогон тестов `backend/tests/rag/test_rag_pipeline_hardening.py`. Ожидаю завершения.

### 🤖 Ассистент

Запущен прогон тестов `backend/tests/rag/test_reranker_hybrid.py`. Ожидаю завершения.

### 🤖 Ассистент

Запущен повторный прогон `backend/tests/rag/test_reranker_hybrid.py`. Ожидаю завершения.

### 🤖 Ассистент

Запущен прогон тестов `backend/tests/rag/test_rag_pipeline_hardening.py`. Ожидаю завершения.

### 🤖 Ассистент

Запущен прогон тестов `backend/tests/rag/test_rag_service.py`. Ожидаю завершения.

### 🤖 Ассистент

Запущен проверочный расчет скора Cross-Encoder. Ожидаю завершения.

### 🤖 Ассистент

Запущен расчет сырого скора модели Cross-Encoder. Ожидаю завершения.

### 🤖 Ассистент

Запущен расчет логитов для релевантной и нерелевантной пары. Ожидаю завершения.

### 🤖 Ассистент

Запущен тестовый расчет. Ожидаю завершения.

### 🤖 Ассистент

Запущен тестовый расчет диапазона логитов. Ожидаю завершения.

### 🤖 Ассистент

Запущен проверочный прогон `backend/tests/rag/test_rag_service.py`. Ожидаю завершения.

### 🤖 Ассистент

Запустил проверку тестов `backend/tests/rag/test_rag_service.py` с обновленной структурой событий потока. Ожидаю завершения выполнения.

### 🤖 Ассистент

Запустил проверку тестов `backend/tests/rag/test_rag_retriever.py`. Ожидаю завершения выполнения.

### 🤖 Ассистент

Запустил сводный прогон ключевых тестовых наборов RAG (`test_reranker_hybrid.py`, `test_rag_pipeline_hardening.py`, `test_rag_service.py`, `test_rag_retriever.py`). Ожидаю завершения.

### 🤖 Ассистент

Запустил выполнение `test_reranker_hybrid.py` с новым тестом RRF. Ожидаю завершения.

### 🤖 Ассистент

Все этапы утвержденного плана реализации успешно выполнены.

Подробный отчет и архитектурные решения зафиксированы в артефактах:
- [walkthrough.md](file:///C:/Users/Дмитрий/.gemini/antigravity-ide/brain/6533c9d8-ca7c-4fb6-8f77-e5c3af926685/walkthrough.md) — сводка внесенных изменений и результаты валидации.
- [docs/adr/ADR_RERANKER.md](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/docs/adr/ADR_RERANKER.md) — архитектурная запись с формулами и матрицей компромиссов.

---

### Что было реализовано:

1. **Weighted Reciprocal Rank Fusion (Weighted RRF, $k=60$)**:
   - Заменено некорректное линейное сложение разнородных шкал на ранговую комбинацию с весами $0.65$ (dense) и $0.35$ (lexical).
   - Сохранены точные бусты за hex-коды (`0x...`) и статьи законов (`ст. 93 44-ФЗ`).

2. **Динамический адаптивный порог Cross-Encoder $T(q)$**:
   - Формула: $T(q) = \text{clamp}(0.28 + 0.015 \cdot \max(0, |q| - 3), 0.28, 0.55)$.
   - Реализован автоматический bypass для hex-ошибок и статей законов.
   - Внедрена калибровка логитов Cross-Encoder с лексическим анкором. При отсечении всех кандидатов система штатно переходит в `degraded_mode`.

3. **Агрегация дочерних чанков в родительские статьи**:
   - Чанки группируются по `node_id` с логарифмическим насыщением вторичных скоров:
     $$S_{\text{parent}} = S_{\max} + 0.10 \cdot \ln\left(1 + \sum S_{\text{other}}\right)$$
   - Итоговая выдача ограничена 5 лучшими уникальными статьями.

4. **Защита от «Lost in the Middle»**:
   - Внедрена U-образная перестановка отобранных статей по схеме $[1, 3, 5, 4, 2]$, располагающая наиболее значимые документы по краям контекстного окна.

5. **Первичный поиск (Recall@30)**:
   - В [Retriever](file:///c:/Users/Дмитрий/OneDrive/Рабочий%20стол/gitos/backend/src/rag/retriever.py) увеличен `top_k` по умолчанию до 30 кандидатов; преждевременная дедупликация снята, чтобы дочерние чанки агрегировались внутри реранкера.

---

### Результаты проверки:
- **Pytest**: **25/25 тестов пройдены успешно** (`test_reranker_hybrid.py`, `test_rag_pipeline_hardening.py`, `test_rag_service.py`, `test_rag_retriever.py`).
- **Ruff**: `All checks passed!`, форматирование и типизация соблюдены в полном объеме.
