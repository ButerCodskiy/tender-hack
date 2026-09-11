# FastAPI Backend Code Standards


## 1. FastAPI Эндпоинты (контроллеры)

### Logic Separation
В эндпоинтах (`@router.get`) не пишем бизнес-логику. Эндпоинт должен только
- Принять данные
- Валидировать
- Передать в Service
- Вернуть ответ

### Dependency Injection
Используем `Depends` для всего (сессии БД, сервисы, пагинация, фильтры, сортировки). Не создаём экземпляры классов внутри эндпоинтов вручную.

Правила
- Все зависимости и алиасы `*Dep` объявляются централизованно в единственном файле `src/api/dependencies.py`. Создание отдельных `dependencies.py` внутри доменных модулей запрещено.
- Функции-провайдеры называем с `get_` (напр. `get_db`, `get_product_service`)
- Используем `Annotated` для создания алиасов (с суффиксом `Dep`) типов. Это убирает дублирование `Depends(...)` в каждом эндпоинте

#### Пример единого файла зависимостей (`src/api/dependencies.py`)

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.database import async_session_maker
from src.products.service import ProductService

async def get_db():
    async with async_session_maker() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_db)]

async def get_product_service(session: SessionDep) -> ProductService:
    return ProductService(session)

ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
```

Использование в роутере:
```python
from fastapi import APIRouter, status
from src.api.dependencies import ProductServiceDep
from src.products.schemas import ProductCreateSchema, ProductResponseSchema

router = APIRouter(prefix="/products", tags=["products"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    product: ProductCreateSchema,
    service: ProductServiceDep,
) -> ProductResponseSchema:
    return await service.create(product)
```

### Status Codes
Числовые литералы запрещены — используются константы `status.HTTP_*` из `fastapi`.
- `POST` — явный `status_code=status.HTTP_201_CREATED`
- `DELETE` — явный `status_code=status.HTTP_204_NO_CONTENT` (с возвратом `None`)
- `GET`, `PUT`, `PATCH` — возвращают код 200 по умолчанию, явное указание не требуется

---

## 2. Pydantic Схемы и Валидация

### Naming
Разделение схем на входные и выходные с суффиксом `Schema`:
- `UserCreateSchema`
- `UserUpdateSchema`
- `UserResponseSchema`

### ORM Mode
В выходных схемах обязателен параметр `model_config = ConfigDict(from_attributes=True)` для сериализации объектов SQLAlchemy.

### Метаданные полей
Описания полей задаются через `Field(description=..., examples=...)` для автоматического формирования OpenAPI.

### Валидаторы
Декоратор `@field_validator` применяется только для проверки формата и типов данных. Запросы к БД и бизнес-правила внутри валидаторов запрещены.

---

## 3. SQLAlchemy 2.0

### Именование
Классы сущностей базы данных имеют суффикс `Model` (например, `ProductModel`). Переменная запроса именуется `stmt` или `query`.

### Syntax
Работаем через ORM и `AsyncSession`:
- Чтение: `session.get(Model, id)` и `session.scalars(select(Model))`
- Запись: `session.add()`, `session.delete()` и мутация атрибутов объекта
- Массовые операции: DML (`insert()`, `update()`, `delete()`) только для bulk-запросов
- Устаревший `session.query()` запрещен

---

## 4. Репозитории

### Naming (Classes)
Классы доступа к данным имеют суффикс `Repository` (например, `ProductRepository`).

### Naming (Methods)
Стандартные методы:
- `get_by_id`
- `get_all` или `get_list` с параметрами фильтрации
- `create`
- `update`
- `delete`

---

## 5. Сервисы и бизнес-логика

### Классы и методы
Классы бизнес-логики имеют суффикс `Service` (например, `ProductService`). Названия методов отражают предметные действия.

### Transactions
Фиксация транзакций (`await session.commit()`) выполняется исключительно в методах сервиса, а не в репозиториях или контроллерах.

---

## 6. Конфигурация приложения (src/main.py)

### Инициализация
Создание экземпляра `FastAPI()` и подключение промежуточных обработчиков сосредоточены только в `src/main.py`.

### CORS
Источники запросов импортируются строго из настроек проекта (`settings.CORS_ORIGINS`). Строковые литералы в коде запрещены.

---

## 7. Общие инженерные стандарты

### Принципы
Соблюдение правил SOLID, DRY, EAFP, Fail Fast и Guard Clauses. Предпочтение отдается плоской структуре без глубокой вложенности.

### Типизация
Обязательны строгие аннотации типов аргументов и возвращаемых значений всех функций.

### Коллекции
Используются стандартные типы Python (`list`, `dict`, `set`, `tuple`) вместо устаревших псевдонимов из модуля `typing`.

### Асинхронность
Для независимых запросов используй `asyncio.TaskGroup` вместо последовательных `await`. 
Так как `AsyncSession` технически не поддерживает конкурентность (вызовет ошибку), при параллельных БД-запросах каждая задача в `TaskGroup` должна создавать свою сессию и свой инстанс репозитория.

### Приватные функции
Внутренние функции и служебные методы классов начинаются с нижнего подчеркивания (`_prepare_payload`).

### Settings
Конфигурация через `pydantic-settings`. Никаких `os.getenv` в глубине кода.

### Docstrings
Публичные модули, классы и сложные методы должны иметь короткие Docstring на русском языке.

### Imports
Импорты для Alembic, которые нужны, но напрямую не используются, нужно писать с `# noqa F401` (например в файле `env.py` для alembic).

### Linter
Единый конфиг `ruff`. Хуки `pre-commit` обязательны.