"""Фильтрация ненормативной лексики и валидация текста сообщений."""

import re
from dataclasses import dataclass
from typing import ClassVar


class ProfanityValidationError(ValueError):
    """Исключение, возникающее при обнаружении ненормативной лексики в сообщении."""

    def __init__(
        self,
        message: str = "Сообщение содержит недопустимую ненормативную лексику.",
        matched_word: str | None = None,
    ) -> None:
        super().__init__(message)
        self.matched_word = matched_word


@dataclass(frozen=True, slots=True)
class ModerationResult:
    """Результат проверки текста модератором."""

    is_profane: bool
    reason: str | None = None
    matched_word: str | None = None


class ProfanityModerator:
    """Детерминированный легковесный модератор обсценной лексики.

    Осуществляет:
    1. Деобфускацию омоглифов латиницы (a->а, c->с, e->е, p->р и др.).
    2. Декодирование leet-speak символов (0->о, @->а, 3->з, 1/!->и, 4->ч, 6->б, $->с).
    3. Сжатие разделителей внутри слов (точки, тире, подчеркивания, звездочки).
    4. Схлопывание повторяющихся подряд символов (бллляяять -> блять).
    5. Защиту легитимных слов русского языка по морфологическому Whitelist (Scunthorpe problem:
       рубль, колебания, употреблять, страхование, мудрый, скипидар и др.).
    6. Сопоставление скомпилированных корней обсценной лексики.
    """

    # Таблица омоглифов (латиница -> кириллица)
    HOMOGLYPHS: ClassVar[dict[str, str]] = {
        "a": "а",
        "b": "в",
        "c": "с",
        "e": "е",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "t": "т",
        "x": "х",
        "y": "у",
    }

    # Таблица leet-speak (числа и спецсимволы -> кириллица)
    LEET_SPEAK: ClassVar[dict[str, str]] = {
        "0": "о",
        "1": "и",
        "@": "а",
        "3": "з",
        "4": "ч",
        "5": "п",
        "6": "б",
        "$": "с",
        "v": "в",
    }

    # Список морфологических основ и легитимных слов для исключения ложных срабатываний
    WHITELIST_PREFIXES: tuple[str, ...] = (
        "рубл",  # рубль, рубля, рублей, рублевка
        "колеб",  # колебания, колеблется, неколебимый
        "употреб",  # употреблять, употребление, злоупотребление
        "страх",  # страхование, застрахуйте, подстраховать, страх
        "мудр",  # мудрый, мудрость, премудрый, замудреный
        "скипидар",
        "оскорб",  # оскорбление, оскорблять
        "парикмахер",
        "педагог",  # педагог, педагогический
        "стебел",  # стебель
        "стебл",  # стебли
        "гребл",  # гребля
        "гребн",  # гребной
        "погреб",
        "выгреб",
        "гребеш",  # гребешок
        "гребти",
        "бляха",  # бляха, бляха-муха, бляшка (разрешено RAG 3.4)
        "блин",  # эмоциональное междометие (разрешено RAG 3.4)
        "черт",  # разрешено RAG 3.4
        "чорт",
        "дубл",  # дубликат, дубль
        "посудомой",  # посудомойка, посудомоечная
        "барсук",  # барсук, барсука
        "хлеб",  # хлеб, хлебный
        "ястреб",  # ястреб
        "робот",
        "ребенок",  # ребенок, ребенка
        "ребят",  # ребята
        "теребит",  # теребить
        "тереблен",
        "психолог",
        "психоз",
        "команд",
        "смущ",  # смущать, смущение
        "возобнов",  # возобновить, возобновление
        "треб",  # требовать, требование, востребован
        "истреб",  # истребить, истребление
        "дебет",  # дебет
        "скреб",  # скребок
        "сукно",  # сукно
        "суккулент",
    )

    def __init__(self) -> None:
        """Компилирует регулярные выражения для обсценных ядер."""
        # Основные корни мата
        self._re_hui = re.compile(
            r"\b\w*(?:х[уо][йяеёюи]|х[уо]е|х[уо]ё|х[уо]и|х[уо]ю|х[уо]ем|х[уо]ев|хуила|хуищ|охуе|ахуе|поху|доху|приху|наху|схуя)\w*\b",
            re.IGNORECASE,
        )
        self._re_pizd = re.compile(
            r"\b\w*(?:пизд|пезд|пизда|пиздец|пиздо|пизди|пиздю|распизд|опизд|пизец|пезец|писдец|песдец|писец)\w*\b",
            re.IGNORECASE,
        )
        self._re_eb = re.compile(
            r"\b(?:\w*еб[аеёиуыю]|еб[аеёиуыю]\w*|ебл[оаяи]|ебан[ыоаеяи]|выеб|заеб|доеб|наеб|отъеб|подъеб|проеб|перееб|въеб|съеб|уеб|еблан|ебыр|ебнут)\w*\b",
            re.IGNORECASE,
        )
        self._re_blyad = re.compile(
            r"\b(?:бл[яеа]д[ьиеяаою]?|бля[тд]ь?|бля)\b",
            re.IGNORECASE,
        )
        self._re_secondary = re.compile(
            r"\b\w*(?:мудак|мудач|мудил|мудозвон|пидор|пидар|педик|пидерист|педераст|гандон|гондон|залуп|манд[аеоу]|сучар)\w*\b",
            re.IGNORECASE,
        )
        # Сука как отдельное оскорбление (не часть барсука или посудомойки)
        self._re_suka = re.compile(
            r"\bс[уе]к[аеиоу]\b",
            re.IGNORECASE,
        )

    def normalize(self, text: str) -> str:
        """Очищает и нормализует текст для обнаружения скрытого мата."""
        if not text:
            return ""

        # 1. Замена латинских букв с диакритикой (акцентами: ý -> y, é -> e, á -> a, ó -> o)
        # Удаляем комбинируемые ударения, но сохраняем букву 'й'
        normalized = text.replace("ý", "y").replace("Ý", "Y")
        normalized = normalized.replace("é", "e").replace("É", "E")
        normalized = normalized.replace("á", "a").replace("Á", "A")
        normalized = normalized.replace("ó", "o").replace("Ó", "O")
        normalized = re.sub(r"[\u0300-\u0305\u0307-\u036f]", "", normalized)

        # 2. Приведение к нижнему регистру и замена ё -> е
        normalized = normalized.lower().replace("ё", "е")

        # 3. Замена ! на и только внутри слов (например, п!здец), чтобы не портить пунктуацию в конце
        normalized = re.sub(
            r"(?<=[а-яa-z0-9])!(?=[а-яa-z0-9])", "и", normalized
        )

        # 4. Декодирование leet-speak
        for leet, cyr in self.LEET_SPEAK.items():
            normalized = normalized.replace(leet, cyr)

        # 5. Замена омоглифов латиницы
        for lat, cyr in self.HOMOGLYPHS.items():
            normalized = normalized.replace(lat, cyr)

        # 6. Удаление внутрисловных разделителей любой длины (точки, подчеркивания, дефисы, звездочки, решетки)
        # Пример: п.и.з.д.е.ц -> пиздец, х_у_й -> хуй, п.и.с*#ец -> писец
        normalized = re.sub(
            r"(?<=[а-яa-z0-9])[\.\-_*~+#@%^&+=/\\|]+(?=[а-яa-z0-9])",
            "",
            normalized,
        )

        # 7. Склеивание разреженных одиночных букв через пробел: "п и з д е ц" -> "пиздец", "х у й" -> "хуй"
        while True:
            new_norm = re.sub(
                r"(?<=\b[а-яa-z])\s+(?=[а-яa-z]\b)", "", normalized
            )
            if new_norm == normalized:
                break
            normalized = new_norm

        # Склеивание устойчивых разреженных корней мата (например: "х уй" -> "хуй", "х уя" -> "хуя")
        normalized = re.sub(r"\bх\s+(?=у[йяеёию])", "х", normalized)

        # 8. Схлопывание повторяющихся подряд символов (более 2 одинаковых подряд -> 1)
        # Пример: блллляяяять -> блять, сууука -> сука, хххуууййй -> хуй
        normalized = re.sub(r"([а-яa-z])\1{2,}", r"\1", normalized)

        return normalized

    def is_whitelisted(self, word: str) -> bool:
        """Проверяет, является ли слово или его основа разрешенным легитимным словом."""
        cleaned_word = word.strip(" .,!?:;\"'()[]{}<>-~*")
        if not cleaned_word:
            return True
        for prefix in self.WHITELIST_PREFIXES:
            if cleaned_word.startswith(prefix) or prefix in cleaned_word:
                return True
        return False

    def check_profanity(self, text: str) -> ModerationResult:
        """Проверяет текст на наличие нецензурной и обсценной лексики."""
        if not text or not text.strip():
            return ModerationResult(is_profane=False)

        normalized = self.normalize(text)

        # Разбиваем нормализованный текст на слова для пословной изоляции Whitelist
        words = re.findall(r"[а-яa-z]+", normalized)

        for word in words:
            # Если слово попадает в Whitelist — пропускаем его
            if self.is_whitelisted(word):
                continue

            # Проверяем на совпадение с паттернами мата
            if self._re_hui.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )
            if self._re_pizd.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )
            if self._re_eb.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )
            if self._re_blyad.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )
            if self._re_secondary.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )
            if self._re_suka.search(word):
                return ModerationResult(
                    is_profane=True,
                    reason="profanity",
                    matched_word=word,
                )

        return ModerationResult(is_profane=False)

    def validate_operator_message(self, text: str) -> None:
        """Проверяет исходящее сообщение оператора на ненормативную лексику.

        Raises:
            ProfanityValidationError: если обнаружен мат.
        """
        result = self.check_profanity(text)
        if result.is_profane:
            raise ProfanityValidationError(
                message=f"Сообщение оператора отклонено: обнаружена недопустимая лексика ('{result.matched_word}').",
                matched_word=result.matched_word,
            )


_moderator: ProfanityModerator | None = None


def get_moderator() -> ProfanityModerator:
    """Возвращает синглтон модератора сообщений."""
    global _moderator
    if _moderator is None:
        _moderator = ProfanityModerator()
    return _moderator
