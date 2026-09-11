"""
Модуль обработки таблиц нормативных документов и регламентов (tables.py).

Реализует:
1. Header Propagation — разворачивание объединенных ячеек (rowspan / colspan)
   с протягиванием контекста родительских категорий в дочерние строки.
2. Двойное представление табличных данных:
   - Для LLM-генерации: чистый Markdown-формат (сохраняется в table_md).
   - Для поискового индекса: плоские факты вида "Колонка: Значение; ...".
"""

import re
from typing import Any


class TableProcessor:
    """Процессор обработки таблиц со сложной структурой и объединенными ячейками."""

    @staticmethod
    def clean_cell_text(text: Any) -> str:
        """Очистка текста ячейки от лишних переносов строк и пробелов."""
        if text is None:
            return ""
        text_str = str(text)
        # Заменяем переносы внутри ячейки на пробелы, убираем множественные пробелы
        text_str = re.sub(r"\s+", " ", text_str).strip()
        # Экранируем символ вертикальной черты для Markdown
        return text_str.replace("|", "\\|")

    @classmethod
    def propagate_headers_from_grid(
        cls,
        raw_rows: list[list[str]],
        row_spans: list[dict[str, int]] | None = None,
    ) -> list[list[str]]:
        """
        Header Propagation для 2D-сетки строк.
        Если передан список spans [{'row': r, 'col': c, 'row_span': rs, 'col_span': cs}],
        значение ячейки протягивается в покрываемые слоты.
        Если явных spans нет, применяется эвристика: если первая колонка (категория)
        пуста в последующих строках, берется значение из строки выше.
        """
        if not raw_rows:
            return []

        # Создаем глубокую копию сетки с очищенным текстом
        grid: list[list[str]] = [
            [cls.clean_cell_text(cell) for cell in row] for row in raw_rows
        ]
        num_rows = len(grid)
        num_cols = max(len(row) for row in grid) if num_rows > 0 else 0

        # Нормализуем длину всех строк
        for row in grid:
            if len(row) < num_cols:
                row.extend([""] * (num_cols - len(row)))

        if row_spans:
            # Точное разворачивание по координатам span
            for span in row_spans:
                r_start = span.get("row", 0)
                c_start = span.get("col", 0)
                r_span = span.get("row_span", 1)
                c_span = span.get("col_span", 1)

                if r_start < num_rows and c_start < num_cols:
                    val = grid[r_start][c_start]
                    for r in range(r_start, min(r_start + r_span, num_rows)):
                        for c in range(
                            c_start, min(c_start + c_span, num_cols)
                        ):
                            grid[r][c] = val
        else:
            # Эвристическое протягивание заголовков категорий по первой и второй колонкам
            for c in range(min(2, num_cols)):
                last_val = ""
                for r in range(num_rows):
                    curr_val = grid[r][c].strip()
                    if curr_val:
                        last_val = curr_val
                    elif (
                        last_val
                        and r > 0
                        and any(
                            grid[r][other] for other in range(c + 1, num_cols)
                        )
                    ):
                        # Протягиваем родительскую категорию, если строка не полностью пустая
                        grid[r][c] = last_val

        return grid

    @classmethod
    def to_markdown(
        cls,
        grid: list[list[str]],
        headers: list[str] | None = None,
    ) -> str:
        """
        Преобразование таблицы в чистый формат Markdown для поля table_md (контекст LLM).
        """
        if not grid and not headers:
            return ""

        effective_headers: list[str] = []
        data_rows: list[list[str]] = []

        if headers:
            effective_headers = [cls.clean_cell_text(h) for h in headers]
            data_rows = grid
        elif grid:
            effective_headers = [cls.clean_cell_text(c) for c in grid[0]]
            data_rows = grid[1:] if len(grid) > 1 else []

        num_cols = len(effective_headers)
        if num_cols == 0:
            return ""

        lines: list[str] = []
        # Заголовочная строка
        lines.append("| " + " | ".join(effective_headers) + " |")
        # Разделитель
        lines.append("| " + " | ".join(["---"] * num_cols) + " |")

        for row in data_rows:
            # Выравниваем строку до нужного числа колонок
            padded_row = [cls.clean_cell_text(c) for c in row]
            if len(padded_row) < num_cols:
                padded_row.extend([""] * (num_cols - len(padded_row)))
            elif len(padded_row) > num_cols:
                padded_row = padded_row[:num_cols]
            lines.append("| " + " | ".join(padded_row) + " |")

        return "\n".join(lines)

    @classmethod
    def to_linearized_facts(
        cls,
        grid: list[list[str]],
        headers: list[str] | None = None,
    ) -> list[str]:
        """
        Преобразование каждой строки таблицы в плоский текстовый факт для векторного поиска.
        Пример: "Сумма: до 3 млн руб.; Размер обеспечения: 0.5%; Срок возврата: 5 рабочих дней"
        """
        if not grid and not headers:
            return []

        effective_headers: list[str] = []
        data_rows: list[list[str]] = []

        if headers:
            effective_headers = [cls.clean_cell_text(h) for h in headers]
            data_rows = grid
        elif grid:
            effective_headers = [cls.clean_cell_text(c) for c in grid[0]]
            data_rows = grid[1:] if len(grid) > 1 else []

        facts: list[str] = []
        for row in data_rows:
            row_facts: list[str] = []
            for col_idx, col_name in enumerate(effective_headers):
                cell_val = row[col_idx] if col_idx < len(row) else ""
                cell_val = cls.clean_cell_text(cell_val)
                if cell_val:
                    if col_name:
                        row_facts.append(f"{col_name}: {cell_val}")
                    else:
                        row_facts.append(cell_val)
            if row_facts:
                facts.append("; ".join(row_facts))

        return facts

    @classmethod
    def process_docling_table(
        cls, docling_table: Any, doc: Any = None
    ) -> tuple[str, list[str]]:
        """
        Адаптер для объекта таблицы Docling (TableItem).
        Извлекает ячейки, учитывает spans, выполняет Header Propagation
        и возвращает пару (table_md, linearized_facts).
        """
        try:
            # 1. Приоритетный путь: экспорт в чистый Markdown через Docling v2
            if hasattr(docling_table, "export_to_markdown"):
                try:
                    table_md = (
                        docling_table.export_to_markdown(doc=doc)
                        if doc is not None
                        else docling_table.export_to_markdown()
                    )
                    if table_md and "|" in table_md:
                        # Разбираем строки Markdown-таблицы в структурированные факты
                        raw_lines = [
                            line.strip()
                            for line in table_md.strip().split("\n")
                            if line.strip()
                        ]
                        rows: list[list[str]] = []
                        for line in raw_lines:
                            if re.match(r"^\|?\s*[-:\s|]+\|?$", line):
                                continue
                            cells = [
                                c.strip() for c in line.strip("|").split("|")
                            ]
                            rows.append(cells)
                        if rows:
                            headers = rows[0]
                            data_rows = rows[1:] if len(rows) > 1 else []
                            grid = cls.propagate_headers_from_grid(data_rows)
                            facts = cls.to_linearized_facts(
                                grid, headers=headers
                            )
                            return table_md, facts
                except Exception:
                    pass

            # 2. Путь через экспорт в DataFrame
            if hasattr(docling_table, "export_to_dataframe"):
                try:
                    df = (
                        docling_table.export_to_dataframe(doc=doc)
                        if doc is not None
                        else docling_table.export_to_dataframe()
                    )
                    headers = [str(c) for c in df.columns]
                    rows = [[str(val) for val in row] for row in df.values]
                    grid = cls.propagate_headers_from_grid(rows)
                    table_md = cls.to_markdown(grid, headers=headers)
                    facts = cls.to_linearized_facts(grid, headers=headers)
                    return table_md, facts
                except Exception:
                    pass

            # 3. Если объект имеет коллекцию cells (Docling AST)
            if hasattr(docling_table, "data") and hasattr(
                docling_table.data, "grid"
            ):
                grid_cells = docling_table.data.grid
                raw_rows: list[list[str]] = []
                for row_cells in grid_cells:
                    raw_rows.append(
                        [
                            getattr(cell, "text", str(cell))
                            for cell in row_cells
                        ]
                    )
                grid = cls.propagate_headers_from_grid(raw_rows)
                table_md = cls.to_markdown(grid)
                facts = cls.to_linearized_facts(grid)
                return table_md, facts

        except Exception:
            pass

        # Фолбэк для текстового представления таблицы
        raw_text = str(docling_table)
        return raw_text, [raw_text] if raw_text.strip() else []
