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

        # 7. Склеивание разреженных одиночных букв через пробел: "п и з д е ц" -> "пиздец", "х у й" -> "хуй", "с у и ц и д" -> "суицид"
        normalized = re.sub(
            r"\b[а-яa-z](?:\s+[а-яa-z])+\b",
            lambda m: m.group(0).replace(" ", "").replace("\t", ""),
            normalized,
        )
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


@dataclass(frozen=True, slots=True)
class SafetyCheckResult:
    """Результат проверки текста фильтрами безопасности."""

    is_safe: bool
    category: str | None = None
    reason: str | None = None
    matched_pattern: str | None = None
    refusal_text: str | None = None


INSTITUTIONAL_SAFETY_REFUSAL = (
    "Виртуальный ассистент Портала поставщиков Москвы консультирует "
    "исключительно по вопросам закупочных процедур (44-ФЗ, 223-ФЗ), регламентам "
    "котировочных сессий и работе в личном кабинете. Обсуждение политических, "
    "религиозных, медицинских тем, а также инструкций опасного или противоправного "
    "характера запрещено регламентом платформы."
)

INSTITUTIONAL_INJECTION_REFUSAL = (
    "Запрос отклонен системой информационной безопасности. Попытка изменения "
    "системных инструкций или выполнения нерегламентированных команд заблокирована. "
    "Пожалуйста, задайте корректный рабочий вопрос по закупкам на Портале поставщиков."
)

INSTITUTIONAL_REPEAT_VIOLATION_REFUSAL = (
    "Обращение завершено в связи с повторным нарушением политик информационной безопасности "
    "и регламентов платформы. Переписка заблокирована и передана на проверку в службу безопасности."
)


class SensitiveTopicsGuardrail:
    """Детерминированный барьер против обсуждения чувствительных и запрещенных тем."""

    # Whitelist закупочных контекстов (для предотвращения ложных срабатываний на медикаменты по 44-ФЗ)
    RE_PROCUREMENT_WHITELIST = re.compile(
        r"\b(?:закупк[а-я]*|поставк[а-я]*|контракт[а-я]*|тендер[а-я]*|аукцион[а-я]*|"
        r"котировочн[а-я]*|оферт[а-я]*|сте\b|еруз\b|44\s*[-‑–—]?\s*фз|223\s*[-‑–—]?\s*фз|"
        r"еаист|реестр[а-я]*|лот[а-я]*|нмцк|спецификаци[а-я]*|техническ[а-я]*\s+задани[а-я]*|"
        r"тз\b|реестров[а-я]*\s+запис[а-я]*|каталог[а-я]*\s+товаров)\b",
        re.IGNORECASE,
    )

    def __init__(self, moderator: ProfanityModerator | None = None) -> None:
        self._moderator = moderator or ProfanityModerator()

        self._re_politics = re.compile(
            r"(?:выбор[а-я]*\s+(?:президента|мэра|депутатов|в\s+госдуму|в\s+рф)|"
            r"политическ[а-я]*\s+(?:парти[а-я]*|взгляд[а-я]*|режим[а-я]*|ситуаци[а-я]*)|"
            r"политик[а-я]*\s+и\s+выбор[а-я]*|"
            r"свергнуть\s+(?:действующ[а-я]*\s+)?правительств[а-я]*|"
            r"свержени[а-я]*\s+власт[а-я]*|государственн[а-я]*\s+переворот[а-я]*|"
            r"митинг[а-я]*|оппозици[а-я]*|путин[а-я]*|навальн[а-я]*|"
            r"зеленск[а-я]*|байден[а-я]*|\bсво\b|специальн[а-я]*\s+военн[а-я]*\s+операци[а-я]*|"
            r"спецопераци[а-я]*|войн[а-я]*\s+с\s+украин[а-я]*|военн[а-я]*\s+действи[а-я]*|"
            r"санкци[а-я]*\s+против\s+росси[а-я]*|политзаключенн[а-я]*|единая\s+росси[а-я]*)",
            re.IGNORECASE,
        )

        self._re_religion = re.compile(
            r"(?:христианств[а-я]*\s+(?:лучше|или|и)\s+ислам[а-я]*|"
            r"ислам[а-я]*\s+(?:лучше|или|и)\s+христианств[а-я]*|"
            r"мусульман[а-я]*\s+или\s+христиан[а-я]*|"
            r"почему\s+.*(?:мусульман|христиан).*не\s+прав|"
            r"какая\s+религи[а-я]*\s+(?:истинн[а-я]*|правильн[а-я]*|лучше)|"
            r"докажи\s+что\s+бог[а-я]*\s+(?:нет|есть)|"
            r"бог[а-я]*\s+(?:нет|есть)\s+на\s+самом\s+деле|"
            r"ваххабизм[а-я]*|шариат[а-я]*|джихад[а-я]*|богохульств[а-я]*|"
            r"сатанизм[а-я]*|сект[а-я]*|свидетел[а-я]*\s+иегов[а-я]*)",
            re.IGNORECASE,
        )

        self._re_drugs = re.compile(
            r"(?:m[3еe]f[3еe]dr[0оo]n[а-я]*|мз[еэ]ф[еэ]др[оа]н[а-я]*|мзфздрон|мефедрон[а-я]*|"
            r"героин[а-я]*|кокаин[а-я]*|амфетамин[а-я]*|"
            r"метамфетамин[а-я]*|метадон[а-я]*|спайс[а-я]*|\bлсд\b|\bэкстази\b|"
            r"марихуан[а-я]*|гашиш[а-я]*|прекурсор[а-я]*|"
            r"синтез\s+(?:наркотик[а-я]*|пав|веществ)|"
            r"(?:рецепт|способ)\s+(?:приготовлени[а-я]*|синтеза|варки)\s+(?:наркотик[а-я]*|пав|веществ)|"
            r"как\s+(?:сварить|приготовить|синтезировать|сделать)\s+(?:наркотик[а-я]*|мет|меф|порошок)|"
            r"закладк[а-я]*\s+(?:с\s+)?[а-я]*|гидропоник[а-я]*\s+для\s+конопли|"
            r"кустарн[а-я]*\s+производств[а-я]*\s+наркотик[а-я]*)",
            re.IGNORECASE,
        )

        self._re_medical_advice = re.compile(
            r"(?:как\s+(?:лечить|вылечить)|"
            r"назначь(?:те)?\s+(?:мне\s+)?(?:лечени[а-я]*|препарат[а-я]*|дозировк[а-я]*)|"
            r"дозировк[а-я]*\s+[а-я]+|"
            r"выпиши(?:те)?\s+рецепт|рецепт\s+(?:на\s+лекарств[а-я]*|врача|приготовлени[а-я]*\s+лекарств)|"
            r"рецепт:\s*принимать|"
            r"какой\s+(?:у\s+меня\s+)?диагноз|поставь(?:те)?\s+диагноз|"
            r"какой\s+антибиотик|"
            r"какие\s+(?:таблетки|лекарства)\s+пить|"
            r"как\s+принимать\s+(?:антибиотик[а-я]*|лекарств[а-я]*|препарат[а-я]*|[а-я]+)|"
            r"болит\s+[а-я]+|колет\s+сердц[а-я]*|симптомы\s+[а-я]+)",
            re.IGNORECASE,
        )

        self._re_self_harm = re.compile(
            r"(?:покончить\s+с\s+собой|суицид[а-я]*|самоубийств[а-я]*|"
            r"вскрыть\s+вены|повеситься|помоги\s+умереть|"
            r"таблетки\s+для\s+(?:смерти|суицида)|"
            r"(?:сброситься|спрыгнуть)\s+с\s+(?:крыши|моста)|"
            r"нанести\s+себе\s+вред)",
            re.IGNORECASE,
        )

        self._re_weapons_extremism = re.compile(
            r"(?:\bсву\b|самодельн[а-я]*\s+взрывн[а-я]*|"
            r"взрывн[а-я]*\s+устройств[а-я]*|"
            r"бомб[а-я]*|взрывчатк[а-я]*|детонатор[а-я]*|"
            r"порох[а-я]*|тротил[а-я]*|гексоген[а-я]*|"
            r"чертеж[а-я]*\s+(?:автомат[а-я]*|оружи[а-я]*)|"
            r"сборк[а-я]*\s+(?:автомат[а-я]*|оружи[а-я]*)|"
            r"как\s+собрать\s+автомат|теракт[а-я]*|взрыв\s+здани[а-я]*|"
            r"захват\s+заложник[а-я]*|массов[а-я]*\s+убийств[а-я]*)",
            re.IGNORECASE,
        )

        self._re_cybercrime = re.compile(
            r"(?:как\s+взломать|взлом[а-я]*\s+(?:сайта|сервера|аккаунта|почты|базы|личного\s+кабинета|системы)|"
            r"ddos\s+атак[а-я]*|ддос\s+атак[а-я]*|"
            r"sql\s*(?:инъекци[а-я]*|injection)|"
            r"эксплойт[а-я]*|украсть\s+парол[а-я]*|"
            r"брутфорс[а-я]*|фишинг[а-я]*)",
            re.IGNORECASE,
        )

    def check_sensitive_topics(self, text: str) -> SafetyCheckResult:
        """Детерминированно проверяет сообщение на наличие запрещенных чувствительных тем."""
        if not text or not text.strip():
            return SafetyCheckResult(is_safe=True)

        normalized = self._moderator.normalize(text)

        # 1. Проверка самоповреждения / суицида (наивысший приоритет, блокируется безусловно)
        m = self._re_self_harm.search(normalized) or self._re_self_harm.search(
            text
        )
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="SUICIDE_SELFHARM",
                reason="Self-harm / suicide trigger detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # 2. Проверка оружия и взрывчатки (безусловная блокировка)
        m = self._re_weapons_extremism.search(
            normalized
        ) or self._re_weapons_extremism.search(text)
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="WEAPONS_EXTREMISM",
                reason="Weapons or explosives instructions detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # 3. Проверка синтеза / рецептуры наркотиков (безусловная блокировка)
        m = self._re_drugs.search(normalized) or self._re_drugs.search(text)
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="DRUGS",
                reason="Drug manufacturing or substances trigger detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # 4. Проверка киберпреступлений (безусловная блокировка)
        m = self._re_cybercrime.search(
            normalized
        ) or self._re_cybercrime.search(text)
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="CYBERCRIME",
                reason="Cybercrime or hacking instructions detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # Проверка контекста госзакупок для предотвращения ложных срабатываний (FPR = 0%)
        # на процедурах поставки медизделий, лекарств, антисептиков и оборудования
        is_procurement = bool(
            self.RE_PROCUREMENT_WHITELIST.search(text)
            or self.RE_PROCUREMENT_WHITELIST.search(normalized)
        )
        if is_procurement:
            return SafetyCheckResult(is_safe=True)

        # 5. Проверка медицинских консультаций / диагнозов (вне контекста закупок)
        m = self._re_medical_advice.search(
            normalized
        ) or self._re_medical_advice.search(text)
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="MEDICINE",
                reason="Medical treatment advice or diagnosis request detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # 6. Проверка политики и геополитики (вне контекста закупок)
        m = self._re_politics.search(normalized) or self._re_politics.search(
            text
        )
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="POLITICS",
                reason="Political or geopolitical controversy detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # 7. Проверка религиозных споров (вне контекста закупок)
        m = self._re_religion.search(normalized) or self._re_religion.search(
            text
        )
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="RELIGION",
                reason="Theological or religious controversy detected",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        return SafetyCheckResult(is_safe=True)


class InjectionAttackDetector:
    """Детерминированный детектор Prompt Injections, Jailbreak атак и сброса инструкций."""

    def __init__(self) -> None:
        self._re_delimiters = re.compile(
            r"(?:</system>|\[/?INST\]|\[/?SYSTEM\]|###\s*(?:Instruction|Human|Assistant):|<prompt>|</prompt>)",
            re.IGNORECASE,
        )
        self._re_ignore_commands = re.compile(
            r"(?:ignore\s+(?:all\s+)?(?:previous|above)\s+(?:instructions|rules|prompts)|"
            r"забудь\s+(?:все\s+)?(?:предыдущие\s+)?(?:инструкции|правила|указания)|"
            r"игнорируй\s+(?:все\s+)?(?:предыдущие\s+)?(?:правила|инструкции|указания)|"
            r"отмени\s+(?:все\s+)?(?:предыдущие\s+)?(?:инструкции|правила))",
            re.IGNORECASE,
        )
        self._re_jailbreak_personas = re.compile(
            r"(?:act\s+as\s+(?:dan|an\s+unfiltered|a\s+jailbroken|an\s+unrestricted)|"
            r"ты\s+теперь\s+(?:dan|свободный\s+ии|не\s+консультант|без\s+ограничений)|"
            r"jailbreak\s+mode|dan\s+mode|unrestricted\s+mode|developer\s+mode\s+enabled)",
            re.IGNORECASE,
        )
        self._re_prompt_leaks = re.compile(
            r"(?:print\s+(?:your\s+)?system\s+prompt|покажи\s+(?:свой\s+)?системный\s+промпт|"
            r"выведи\s+системный\s+промпт|раскрой\s+системные\s+инструкции)",
            re.IGNORECASE,
        )
        self._re_new_rules = re.compile(
            r"(?:new\s+system\s+instructions?:|новые\s+правила\s*:\s*ты\s+обязан|с\s+этого\s+момента\s+ты)",
            re.IGNORECASE,
        )

    def check_injection(self, text: str) -> SafetyCheckResult:
        """Проверяет входящий текст на паттерны prompt injection и джейлбрейков."""
        if not text or not text.strip():
            return SafetyCheckResult(is_safe=True)

        for pattern, cat, reason in [
            (
                self._re_delimiters,
                "PROMPT_INJECTION",
                "Structural tag injection detected",
            ),
            (
                self._re_ignore_commands,
                "PROMPT_INJECTION",
                "Instruction override directive detected",
            ),
            (
                self._re_jailbreak_personas,
                "JAILBREAK",
                "Jailbreak / DAN persona trigger detected",
            ),
            (
                self._re_prompt_leaks,
                "PROMPT_LEAK",
                "System prompt extraction attempt detected",
            ),
            (
                self._re_new_rules,
                "PROMPT_INJECTION",
                "Adversarial rule imposition detected",
            ),
        ]:
            m = pattern.search(text)
            if m:
                return SafetyCheckResult(
                    is_safe=False,
                    category=cat,
                    reason=reason,
                    matched_pattern=m.group(0),
                    refusal_text=INSTITUTIONAL_INJECTION_REFUSAL,
                )

        return SafetyCheckResult(is_safe=True)


class OutputSafetyGuardrail:
    """Выходной фильтр для контроля сгенерированных моделью ответов до отправки клиенту."""

    def __init__(
        self, sensitive_guard: SensitiveTopicsGuardrail | None = None
    ) -> None:
        self._sensitive_guard = sensitive_guard or SensitiveTopicsGuardrail()
        self._re_dan_affirmation = re.compile(
            r"(?:I\s+am\s+DAN|As\s+an\s+unrestricted\s+AI|Я\s+теперь\s+DAN|Я\s+свободный\s+ИИ)",
            re.IGNORECASE,
        )

    def validate_output(self, output_text: str) -> SafetyCheckResult:
        """Проверяет сгенерированный текст на безопасность перед отправкой пользователю."""
        if not output_text or not output_text.strip():
            return SafetyCheckResult(is_safe=True)

        # Проверка утверждения вредоносной персоны
        m = self._re_dan_affirmation.search(output_text)
        if m:
            return SafetyCheckResult(
                is_safe=False,
                category="JAILBREAK_OUTPUT",
                reason="Model adopted jailbreak persona",
                matched_pattern=m.group(0),
                refusal_text=INSTITUTIONAL_SAFETY_REFUSAL,
            )

        # Проверка чувствительных тем
        return self._sensitive_guard.check_sensitive_topics(output_text)


_moderator: ProfanityModerator | None = None
_sensitive_guardrail: SensitiveTopicsGuardrail | None = None
_injection_detector: InjectionAttackDetector | None = None
_output_guardrail: OutputSafetyGuardrail | None = None


def get_moderator() -> ProfanityModerator:
    """Возвращает синглтон модератора сообщений."""
    global _moderator
    if _moderator is None:
        _moderator = ProfanityModerator()
    return _moderator


def get_sensitive_guardrail() -> SensitiveTopicsGuardrail:
    """Возвращает синглтон фильтра чувствительных тем."""
    global _sensitive_guardrail
    if _sensitive_guardrail is None:
        _sensitive_guardrail = SensitiveTopicsGuardrail()
    return _sensitive_guardrail


def get_injection_detector() -> InjectionAttackDetector:
    """Возвращает синглтон детектора Prompt Injection."""
    global _injection_detector
    if _injection_detector is None:
        _injection_detector = InjectionAttackDetector()
    return _injection_detector


def get_output_guardrail() -> OutputSafetyGuardrail:
    """Возвращает синглтон выходного фильтра безопасности."""
    global _output_guardrail
    if _output_guardrail is None:
        _output_guardrail = OutputSafetyGuardrail()
    return _output_guardrail
