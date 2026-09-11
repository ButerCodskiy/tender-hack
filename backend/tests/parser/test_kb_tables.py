"""
Тесты обработки таблиц, Header Propagation и линеаризации (test_kb_tables.py).
"""

from src.kb.tables import TableProcessor


def test_header_propagation():
    raw_table = [
        ["Категория", "НМЦК", "Обеспечение"],
        ["Котировочные сессии", "до 600 тыс.", "нет"],
        ["", "от 600 тыс. до 3 млн", "0.5%"],
        ["", "от 3 млн до 5 млн", "1.0%"],
        ["Малые закупки", "до 100 тыс.", "нет"],
    ]

    propagated = TableProcessor.propagate_headers_from_grid(raw_table)
    # Проверяем протягивание категории
    assert propagated[1][0] == "Котировочные сессии"
    assert propagated[2][0] == "Котировочные сессии"
    assert propagated[3][0] == "Котировочные сессии"
    assert propagated[4][0] == "Малые закупки"


def test_table_markdown_generation():
    grid = [
        ["Колонка 1", "Колонка 2"],
        ["Значение A", "Значение B"],
    ]
    md = TableProcessor.to_markdown(grid)
    assert "| Колонка 1 | Колонка 2 |" in md
    assert "| --- | --- |" in md
    assert "| Значение A | Значение B |" in md


def test_table_linearization():
    grid = [
        ["Услуга", "Тариф", "Срок"],
        ["Доставка", "500 руб.", "1 день"],
        ["Сборка", "1000 руб.", "2 дня"],
    ]
    facts = TableProcessor.to_linearized_facts(grid)
    assert len(facts) == 2
    assert facts[0] == "Услуга: Доставка; Тариф: 500 руб.; Срок: 1 день"
    assert facts[1] == "Услуга: Сборка; Тариф: 1000 руб.; Срок: 2 дня"
