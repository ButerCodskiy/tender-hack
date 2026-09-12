import { Citation } from '../types/chat';
import { AuthTokens, UserProfile } from '../types/auth';
import { ActiveTicketSummary, BackendChatState, ClientResolveTicketResponse, StreamCallbacks } from './api';

const MOCK_STORAGE_CHAT_KEY = 'portal_mock_chat_state';

// База знаний для моковых ответов
interface MockTopicAnswer {
  keywords: string[];
  title: string;
  sources: Citation[];
  response: string;
}

const MOCK_KNOWLEDGE_BASE: MockTopicAnswer[] = [
  {
    keywords: ['крипто', 'эцп', 'плагин', 'подпис', 'сертификат'],
    title: 'Настройка электронной подписи и КриптоПро ЭЦП Browser Plug-in',
    sources: [
      {
        id: 'chunk-crypto-p1',
        title: 'Регламент Портала поставщиков. Раздел 3. Требования к ЭЦП',
        sectionPath: 'docs/regulations/crypto_plugin_setup.md',
        excerpt: 'Для работы на Портале поставщиков требуется усиленная квалифицированная электронная подпись (УКЭП), выданная аккредитованным УЦ ФНС России, и плагин КриптоПро версии не ниже 2.0.14500.',
      },
      {
        id: 'chunk-crypto-p2',
        title: 'Инструкция по устранению ошибок валидации сертификата',
        sectionPath: 'docs/guides/cryptopro_troubleshooting.md',
        excerpt: 'При ошибке 0x80090014 очистите SSL-кэш в браузере, перезапустите службу веб-клиента и проверьте доступность списка отозванных сертификатов (CRL).',
      },
    ],
    response:
      'Для корректного подписания документов на Портале поставщиков выполните следующие действия:\n\n' +
      '1. **Убедитесь в наличии актуальной версии плагина:** Установите *КриптоПро ЭЦП Browser Plug-in* (версия 2.0.15000 или выше) с официального сайта разработчика.\n' +
      '2. **Проверьте расширение в браузере:** Включите расширение CryptoPro Extension for CAdES Browser Plug-in в используемом браузере (Яндекс.Браузер, Chromium-Gost, Chrome).\n' +
      '3. **Добавьте сайт в доверенные узлы:** В настройках плагина добавьте адрес `zakupki.mos.ru` в список доверенных узлов.\n' +
      '4. **Проверьте сертификат:** Срок действия УКЭП и установленный корневой сертификат Минцифры России должны быть действительны.\n\n' +
      'Если ошибка сохраняется, нажмите кнопку «Вызвать оператора», и специалист 2-й линии поможет диагностировать проблему в режиме удаленного сопровождения.',
  },
  {
    keywords: ['котировочн', 'сесси', 'ставка', 'оферт', 'снижени'],
    title: 'Участие в котировочных сессиях и подача ценовых предложений',
    sources: [
      {
        id: 'chunk-quotation-s1',
        title: 'Регламент проведения котировочных сессий (44-ФЗ)',
        sectionPath: 'docs/regulations/quotation_sessions.md',
        excerpt: 'Длительность стандартной котировочной сессии составляет 3, 6 или 24 часа. Шаг снижения ценового предложения составляет от 0.5% до 5% от начальной (максимальной) цены контракта (НМЦК).',
      },
      {
        id: 'chunk-quotation-s2',
        title: 'Правила автоматического продления котировочных сессий',
        sectionPath: 'docs/regulations/anti_sniping_rules.md',
        excerpt: 'Если ценовое предложение поступило менее чем за 5 минут до окончания сессии, время приема продлевается на 5 минут.',
      },
    ],
    response:
      'Порядок участия и подачи ценовых предложений в котировочных сессиях на Портале:\n\n' +
      '• **Сроки сессии:** Стандартные котировочные сессии проводятся в течение 3, 6 или 24 часов в соответствии с графиком заказчика.\n' +
      '• **Шаг ставки:** Поставщик может снижать цену с шагом от 0.5% до 5% от НМЦК. Каждая последующая ставка должна быть строго ниже текущей лучшей цены.\n' +
      '• **Автопродление:** Подача оферты на последних 5 минутах автоматически продлевает сессию еще на 5 минут (правило анти-снайпинга).\n' +
      '• **Обеспечение заявки:** Для участия убедитесь в отсутствии блокировок и актуальности вашей выписки из ЕГРЮЛ/ЕГРИП в ЕРУЗ.\n\n' +
      'После окончания сессии протокол подведения итогов формируется автоматически в течение 1 часа.',
  },
  {
    keywords: ['мчд', 'доверенност', 'полномоч', 'фнс', 'реестр'],
    title: 'Привязка машиночитаемой доверенности (МЧД) из реестра ФНС',
    sources: [
      {
        id: 'chunk-mchd-art1',
        title: 'Порядок работы с машиночитаемыми доверенностями (версия 003)',
        sectionPath: 'docs/regulations/mchd_guidelines.md',
        excerpt: 'С 1 сентября 2024 года подписание от имени организации физическим лицом требует обязательного указания GUID доверенности из распределенного реестра ФНС России.',
      },
    ],
    response:
      'Инструкция по регистрации и привязке МЧД сотрудника:\n\n' +
      '1. Доверенность единого формата (версия 003) должна быть предварительно зарегистрирована руководителем в распределенном реестре ФНС России.\n' +
      '2. В Личном кабинете Портала поставщиков перейдите в раздел **«Организация» → «Сотрудники и МЧД»**.\n' +
      '3. Нажмите кнопку **«Добавить МЧД»** и укажите единый регистрационный номер (GUID доверенности) и ИНН доверителя.\n' +
      '4. Система выполнит автоматическую проверку статуса в реестре ФНС (занимает от 30 секунд до 2 минут).\n' +
      '5. После валидации полномочия на подписание контрактов и подачу оферт активируются немедленно.',
  },
  {
    keywords: ['разноглас', 'протокол', 'срок', 'контракт', 'замечан'],
    title: 'Регламент направления протокола разногласий по контракту',
    sources: [
      {
        id: 'chunk-dispute-p1',
        title: 'Регламент заключения контракта. Раздел 5. Протокол разногласий',
        sectionPath: 'docs/regulations/contract_disputes.md',
        excerpt: 'Поставщик вправе направить протокол разногласий заказчику один раз не позднее 1 рабочего дня с даты размещения проекта контракта в ЕИС/на Портале.',
      },
    ],
    response:
      'Регламентные условия направления протокола разногласий:\n\n' +
      '• **Срок подачи:** Не позднее **1 рабочего дня** с момента размещения заказчиком проекта контракта в карточке закупки.\n' +
      '• **Допустимые основания:** Несоответствие проекта контракта извещению о котировочной сессии, проекту контракта из документации или оферте победителя.\n' +
      '• **Порядок действий:** В карточке контракта выберите действие *«Сформировать протокол разногласий»*, прикрепите файл с обоснованием замечаний и подпишите УКЭП.\n' +
      '• Заказчик обязан рассмотреть протокол в течение 2 рабочих дней и направить скорректированный проект либо отказ с обоснованием.',
  },
];

const DEFAULT_ANSWER: MockTopicAnswer = {
  keywords: [],
  title: 'Общая консультация по регламенту Портала поставщиков',
  sources: [
    {
      id: 'chunk-general-1',
      title: 'Единый регламент функционирования Портала поставщиков г. Москвы',
      sectionPath: 'docs/regulations/general_portal_rules.md',
      excerpt: 'Портал поставщиков обеспечивает автоматизацию процедур закупок малого объема в соответствии с нормами Федерального закона № 44-ФЗ и Федерального закона № 223-ФЗ.',
    },
    {
      id: 'chunk-general-2',
      title: 'Справочник типовых регламентных процедур поставщика',
      sectionPath: 'docs/regulations/faq_standard_procedures.md',
      excerpt: 'Все операции на Портале фиксируются в журнале аудита действий пользователей с фиксацией точного времени по московскому часовому поясу (UTC+3).',
    },
  ],
  response:
    'Спасибо за обращение! Согласно регламенту Портала поставщиков:\n\n' +
    '• Все процедуры закупок малого объема осуществляются в строгом соответствии с 44-ФЗ и 223-ФЗ.\n' +
    '• Для юридически значимых действий требуется действующая УКЭП руководителя или уполномоченного лица с зарегистрированной МЧД.\n' +
    '• Если вам требуется детальный разбор конкретной ситуации или возникла техническая ошибка в карточке контракта, вы можете в любой момент нажать кнопку **«Вызвать оператора»** для подключения дежурного инженера поддержки.',
};

function findKnowledgeAnswer(query: string): MockTopicAnswer {
  const lower = query.toLowerCase();
  for (const item of MOCK_KNOWLEDGE_BASE) {
    if (item.keywords.some((kw) => lower.includes(kw))) {
      return item;
    }
  }
  return DEFAULT_ANSWER;
}

/**
 * Имитация потокового ответа нейросети в автономном визуальном режиме
 */
export async function simulateMockChatStream(
  content: string,
  callbacks: StreamCallbacks
): Promise<void> {
  const lower = content.toLowerCase();
  const profanityPatterns = [
    /ху[йеяиюё]/i,
    /пизд/i,
    /еб[аеёиуыл]/i,
    /бл[яе]/i,
    /сук[аи]/i,
    /муда[кч]/i,
    /пидор/i,
    /гондон/i,
    /шлюх/i,
  ];
  if (profanityPatterns.some((p) => p.test(lower))) {
    await delay(300);
    callbacks.onSessionTerminated?.(
      'profanity',
      'Ваше обращение завершено в связи с нарушением правил общения (использование нецензурной лексики). Пожалуйста, сформируйте новое обращение в корректной форме.'
    );
    return;
  }

  const answerData = findKnowledgeAnswer(content);

  // Шаг 1: Статус поиска
  callbacks.onStatus?.('Поиск по базе регламентов Портала поставщиков...');
  await delay(350);

  // Шаг 2: Статус ранжирования
  callbacks.onStatus?.('Анализ нормативных актов и статей 44-ФЗ...');
  await delay(400);

  // Шаг 3: Цитаты / Источники
  callbacks.onSources?.(answerData.sources);
  await delay(250);

  // Шаг 4: Потоковый вывод текста ответа
  const text = answerData.response;
  const words = text.split(' ');
  let accumulated = '';

  for (let i = 0; i < words.length; i++) {
    const chunk = (i === 0 ? '' : ' ') + words[i];
    accumulated += chunk;
    callbacks.onChunk?.(chunk);
    // Небольшая случайная пауза для реалистичности стриминга токенов
    await delay(18 + Math.floor(Math.random() * 20));
  }

  // Шаг 5: Завершение
  await delay(100);
  const mockMessageId = `mock-msg-${Date.now()}`;
  const mockTicketId = `mock-ticket-${Date.now()}`;
  callbacks.onDone?.(accumulated, mockMessageId, mockTicketId);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Получение мокового состояния чата из локального хранилища
 */
export function getMockChatState(): BackendChatState {
  try {
    const raw = localStorage.getItem(MOCK_STORAGE_CHAT_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}

  const defaultState: BackendChatState = {
    chat_id: 'mock-chat-01',
    active_ticket: {
      id: 'mock-t-100',
      status: 'bot_processing',
      priority: 'P1',
      line_code: 'L1',
      assigned_operator_name: null,
      created_at: new Date().toISOString(),
    },
    messages: [
      {
        id: 'mock-m-welcome',
        ticket_id: 'mock-t-100',
        sender_type: 'bot',
        sender_name: 'ИИ-Ассистент Портала Поставщиков',
        sender_role: 'bot',
        text: 'Здравствуйте! Я интеллектуальный ассистент службы поддержки Портала поставщиков. Задайте любой вопрос по регламенту котировочных сессий, настройке электронной подписи или исполнению контрактов.',
        created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
        sources: [
          {
            chunk_id: 'chunk-welcome',
            doc_id: 'Регламент Портала поставщиков',
            quote_text: 'Служба поддержки пользователей функционирует круглосуточно.',
          },
        ],
      },
    ],
    can_escalate: true,
    can_cancel: false,
    can_feedback: false,
  };

  saveMockChatState(defaultState);
  return defaultState;
}

export function saveMockChatState(state: BackendChatState): void {
  try {
    localStorage.setItem(MOCK_STORAGE_CHAT_KEY, JSON.stringify(state));
  } catch {}
}

/**
 * Моковая эскалация тикета к оператору
 */
export function mockEscalateTicket(): ActiveTicketSummary {
  const state = getMockChatState();
  const summary: ActiveTicketSummary = {
    id: state.active_ticket?.id || `mock-t-${Date.now()}`,
    status: 'assigned',
    priority: 'P1',
    line_code: 'L1',
    assigned_operator_name: 'Смирнова Анна Сергеевна',
    created_at: new Date().toISOString(),
  };

  state.active_ticket = summary;
  state.messages.push({
    id: `mock-sys-${Date.now()}`,
    ticket_id: summary.id,
    sender_type: 'system',
    text: 'Диалог переведен на 1-ю линию поддержки. Оператор Смирнова А.С. подключилась к обращению.',
    created_at: new Date().toISOString(),
  });
  state.messages.push({
    id: `mock-op-${Date.now() + 1}`,
    ticket_id: summary.id,
    sender_type: 'operator',
    sender_name: 'Смирнова Анна Сергеевна',
    sender_role: 'operator',
    text: 'Здравствуйте! Меня зовут Анна, я специалист службы поддержки 1-й линии. Ознакомилась с контекстом вашего обращения, сейчас помогу решить проблему.',
    created_at: new Date(Date.now() + 1000).toISOString(),
  });

  saveMockChatState(state);
  return summary;
}

/**
 * Моковое завершение тикета клиентом
 */
export function mockResolveTicket(ticketId: string): ClientResolveTicketResponse {
  const state = getMockChatState();
  if (state.active_ticket && state.active_ticket.id === ticketId) {
    state.active_ticket.status = 'resolved';
  }
  state.can_feedback = true;
  state.feedback_ticket_id = ticketId;
  saveMockChatState(state);

  return {
    status: 'resolved',
    ticket_id: ticketId,
    closed_at: new Date().toISOString(),
  };
}

/**
 * Моковая отправка CSAT отзыва
 */
export function mockSubmitFeedback(ticketId: string, score: number, comment?: string): void {
  const state = getMockChatState();
  state.can_feedback = false;
  state.feedback_ticket_id = null;
  saveMockChatState(state);
  console.log(`[Mock CSAT Feedback] Ticket: ${ticketId}, Score: ${score}, Comment: ${comment || 'none'}`);
}

/**
 * Генерация токенов авторизации для демо-пользователя в автономном режиме
 */
export function generateMockAuthTokens(user: Partial<UserProfile>): AuthTokens {
  const userProfile: UserProfile = {
    id: user.id || `mock-usr-${Date.now()}`,
    role_code: user.role_code || 'client',
    email: user.email || 'supplier@example.com',
    full_name: user.full_name || 'Иванов Иван Иванович',
    company_name: user.company_name || 'ООО «ТехноСнаб Поставка»',
    inn: user.inn || '7701234567',
    line_code: user.line_code,
    created_at: new Date().toISOString(),
  };

  return {
    access_token: `mock_jwt_access_${Date.now()}`,
    refresh_token: `mock_jwt_refresh_${Date.now()}`,
    token_type: 'bearer',
    expires_in: 86400,
    user: userProfile,
  };
}
