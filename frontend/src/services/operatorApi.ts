import {
  OperatorProfile,
  OperatorSidebarTicket,
  OperatorTicketWorkspace,
  ShiftStatus,
} from '../types/operator';
import { Message } from '../types/chat';
import { getStoredTokens, getStoredUser } from './auth';
import { isStandaloneMode } from '../config/mode';

const STORAGE_SHIFT_KEY = 'portal_operator_shift';
const STORAGE_TICKETS_KEY = 'portal_operator_tickets';
const STORAGE_WORKSPACES_KEY = 'portal_operator_workspaces';

export function getOperatorLineCode(): 'L1' | 'L2' | 'L3' {
  const user = getStoredUser();
  if (user?.email === 'operator2@example.com' || user?.line_code === 'L2') return 'L2';
  if (user?.email === 'operator3@example.com' || user?.line_code === 'L3') return 'L3';
  return 'L1';
}

export function getOperatorProfileForUser(): OperatorProfile {
  const user = getStoredUser();
  const line = getOperatorLineCode();
  const rawShift = localStorage.getItem(`${STORAGE_SHIFT_KEY}_${line}`) as ShiftStatus | null;

  if (line === 'L2') {
    return {
      user_id: user?.id || 'op-002',
      full_name: user?.full_name || 'Кузнецов Петр Васильевич',
      line_id: 2,
      line_code: 'L2',
      shift_status: rawShift || 'active',
      max_slots: 5,
      active_slots_count: 3,
    };
  }
  if (line === 'L3') {
    return {
      user_id: user?.id || 'op-003',
      full_name: user?.full_name || 'Соколова Елена Дмитриевна',
      line_id: 3,
      line_code: 'L3',
      shift_status: rawShift || 'active',
      max_slots: 5,
      active_slots_count: 3,
    };
  }
  return {
    user_id: user?.id || 'op-001',
    full_name: user?.full_name || 'Смирнова Анна Сергеевна',
    line_id: 1,
    line_code: 'L1',
    shift_status: rawShift || 'active',
    max_slots: 5,
    active_slots_count: 3,
  };
}

const DEFAULT_TICKETS_L1: OperatorSidebarTicket[] = [
  {
    ticket_id: 't-101',
    chat_id: 'c-101',
    priority: 'P1',
    status: 'assigned',
    line_code: 'L1',
    client_name: 'Иванов И.И.',
    company_name: 'ООО «ТехноСнаб»',
    last_message_preview: 'Не подгружается машиночитаемая доверенность (МЧД) из реестра ФНС.',
    unread_messages_count: 1,
    created_at: '15 мин. назад',
    assigned_at: '5 мин. назад',
  },
  {
    ticket_id: 't-102',
    chat_id: 'c-102',
    priority: 'P2',
    status: 'in_progress',
    line_code: 'L1',
    client_name: 'Петров С.Н.',
    company_name: 'ООО «КанцТорг»',
    last_message_preview: 'Ошибка импорта YML: тег <param name="Цвет"> не проходит валидацию.',
    unread_messages_count: 0,
    created_at: '35 мин. назад',
    assigned_at: '20 мин. назад',
  },
  {
    ticket_id: 't-103',
    chat_id: 'c-103',
    priority: 'P2',
    status: 'in_progress',
    line_code: 'L1',
    client_name: 'Смирнов А.В.',
    company_name: 'ИП Смирнов А.В.',
    last_message_preview: 'Подскажите порядок и сроки направления протокола разногласий.',
    unread_messages_count: 0,
    created_at: '1 час назад',
    assigned_at: '30 мин. назад',
  },
];

const DEFAULT_TICKETS_L2: OperatorSidebarTicket[] = [
  {
    ticket_id: 't-201',
    chat_id: 'c-201',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L2',
    client_name: 'Кузнецов В.А.',
    company_name: 'ООО «ПромСервис Поставка»',
    last_message_preview: 'Срочно! Котировочная сессия КС-9482, ошибка КриптоПро 0x80090016.',
    unread_messages_count: 2,
    created_at: '8 мин. назад',
    assigned_at: 'Только что',
  },
  {
    ticket_id: 't-202',
    chat_id: 'c-202',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L2',
    client_name: 'Морозов Д.К.',
    company_name: 'ООО «СтройКомплект»',
    last_message_preview: 'Не могу прикрепить УПД к контракту №9923/26. Ошибка формата по приказу 820.',
    unread_messages_count: 1,
    created_at: '25 мин. назад',
    assigned_at: '15 мин. назад',
  },
  {
    ticket_id: 't-203',
    chat_id: 'c-203',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L2',
    client_name: 'Васильева О.П.',
    company_name: 'АО «МедСнабжение»',
    last_message_preview: 'Окно плагина КриптоПро зависает на этапе вызова функции SignHash.',
    unread_messages_count: 0,
    created_at: '45 мин. назад',
    assigned_at: '20 мин. назад',
  },
];

const DEFAULT_TICKETS_L3: OperatorSidebarTicket[] = [
  {
    ticket_id: 't-301',
    chat_id: 'c-301',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L3',
    client_name: 'Зайцев Е.М.',
    company_name: 'ООО «ИнфоТех»',
    last_message_preview: 'Авария: отказ интеграционного шлюза ЕАИСТ / ЭДО Диадок, зависли пакеты УПД.',
    unread_messages_count: 3,
    created_at: '5 мин. назад',
    assigned_at: 'Только что',
  },
  {
    ticket_id: 't-302',
    chat_id: 'c-302',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L3',
    client_name: 'Белов А.С.',
    company_name: 'ООО «ДатаГрупп»',
    last_message_preview: 'Зависание очереди асинхронного парсера YML-каталога в Redis.',
    unread_messages_count: 1,
    created_at: '30 мин. назад',
    assigned_at: '10 мин. назад',
  },
  {
    ticket_id: 't-303',
    chat_id: 'c-303',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L3',
    client_name: 'Романова К.И.',
    company_name: 'ООО «ИТ-Решения»',
    last_message_preview: 'Ошибка 502 Bad Gateway при массовой выгрузке закрывающих протоколов.',
    unread_messages_count: 0,
    created_at: '55 мин. назад',
    assigned_at: '25 мин. назад',
  },
];

const DEFAULT_WORKSPACES_L1: Record<string, OperatorTicketWorkspace> = {
  't-101': {
    ticket_id: 't-101',
    chat_id: 'c-101',
    priority: 'P1',
    status: 'assigned',
    line_code: 'L1',
    client: {
      company_name: 'ООО «ТехноСнаб»',
      inn: '7701234567',
      kpp: '770101001',
      phone: '+7 (495) 345-67-89',
      full_name: 'Иванов Иван Иванович',
      email: 'supplier@technosnab.ru',
    },
    copilot_summary: {
      summary: 'Проблема синхронизации машиночитаемой доверенности (МЧД) версии 003 из распределенного реестра ФНС.',
      suggested_line_code: 'L1',
      suggested_response: 'Здравствуйте, Иван Иванович! Проверили статус доверенности в распределенном реестре ФНС. Для успешной привязки МЧД в личном кабинете Портала поставщиков убедитесь, что в профиле сотрудника указан СНИЛС, в точности совпадающий с доверенностью.',
      recommended_chunk_ids: ['chunk-mchd-reg-art4'],
      similar_resolved_tickets: [
        {
          ticket_id: 't-071',
          support_line: 'L1',
          user_query: 'Как привязать МЧД сотрудника',
          solution_text: 'Сверка СНИЛС и повторный запрос проверки полномочий через ЕСИА.',
          similarity_score: 0.91,
        },
      ],
    },
    messages: [
      {
        id: 'm-101-1',
        content: 'Добрый день. Пытаюсь загрузить МЧД из реестра ФНС, пишет «Доверенность не найдена или не активна». Но в ФНС статус «Зарегистрирована».',
        type: 'user',
        timestamp: '14:50',
        actions: [],
      },
    ],
  },
  't-102': {
    ticket_id: 't-102',
    chat_id: 'c-102',
    priority: 'P2',
    status: 'in_progress',
    line_code: 'L1',
    client: {
      company_name: 'ООО «КанцТорг»',
      inn: '7702847510',
      phone: '+7 (495) 912-34-56',
      full_name: 'Петров Сергей Николаевич',
      email: 'petrov@kanctorg.ru',
    },
    copilot_summary: {
      summary: 'Ошибка импорта каталога YML: тег <param name="Цвет"> не проходит валидацию на строке 48.',
      suggested_line_code: 'L1',
      suggested_response: 'Здравствуйте, Сергей Николаевич! Проверил ваш файл: в категории "Канцтовары" параметр "Цвет" требует выбора предопределенного значения из классификатора Портала. Замените текстовое описание цвета на соответствующий ID.',
      recommended_chunk_ids: ['chunk-yml-import-rules'],
    },
    messages: [
      {
        id: 'm-102-1',
        content: 'Ошибка импорта YML: тег <param name="Цвет"> не проходит валидацию на строке 48. Как загрузить оферты в каталог?',
        type: 'user',
        timestamp: '14:30',
        actions: [],
      },
    ],
  },
  't-103': {
    ticket_id: 't-103',
    chat_id: 'c-103',
    priority: 'P2',
    status: 'in_progress',
    line_code: 'L1',
    client: {
      company_name: 'ИП Смирнов А.В.',
      inn: '772345678901',
      phone: '+7 (916) 123-45-67',
      full_name: 'Смирнов Алексей Викторович',
      email: 'smirnov@mail.ru',
    },
    copilot_summary: {
      summary: 'Консультация по регламентным срокам подачи протокола разногласий по котировочной сессии 44-ФЗ.',
      suggested_line_code: 'L1',
      suggested_response: 'Здравствуйте, Алексей Викторович! Согласно Регламенту Портала поставщиков (п. 5.3), протокол разногласий может быть направлен в течение 1 рабочего дня с момента публикации проекта контракта заказчиком.',
      recommended_chunk_ids: ['chunk-dispute-reg-sec5'],
    },
    messages: [
      {
        id: 'm-103-1',
        content: 'Здравствуйте, подскажите, в какой срок поставщик имеет право направить протокол разногласий?',
        type: 'user',
        timestamp: '14:15',
        actions: [],
      },
    ],
  },
};

const DEFAULT_WORKSPACES_L2: Record<string, OperatorTicketWorkspace> = {
  't-201': {
    ticket_id: 't-201',
    chat_id: 'c-201',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L2',
    client: {
      company_name: 'ООО «ПромСервис Поставка»',
      inn: '7701984512',
      kpp: '770101001',
      phone: '+7 (495) 780-12-34',
      full_name: 'Кузнецов Валерий Алексеевич',
      email: 'kuznetsov@promservice.ru',
    },
    copilot_summary: {
      summary: 'Критический сбой плагина КриптоПро 0x80090016 при подписании оферты котировочной сессии КС-9482.',
      suggested_line_code: 'L2',
      suggested_response: 'Здравствуйте, Валерий Алексеевич! Ошибка 0x80090016 указывает на невозможность считывания закрытого ключа. Переподключите USB-токен Рутокен, перезапустите службу "КриптоПро CSP" и убедитесь, что в хранилище установлены корневые сертификаты УЦ ФНС.',
      recommended_chunk_ids: ['chunk-crypto-p1', 'chunk-crypto-p2'],
      similar_resolved_tickets: [
        {
          ticket_id: 't-084',
          support_line: 'L2',
          user_query: 'Ошибка 0x80090016 КриптоПро при подписании',
          solution_text: 'Переустановка корневых сертификатов Минцифры и очистка SSL-кэша браузера.',
          similarity_score: 0.96,
        },
      ],
    },
    messages: [
      {
        id: 'm-201-1',
        content: 'Срочно! Идет котировочная сессия КС-9482, не могу подписать оферту! Ошибка плагина: 0x80090016 Набор ключей не существует. Сессия закроется через 20 минут!',
        type: 'user',
        timestamp: '15:10',
        actions: [],
      },
    ],
  },
  't-202': {
    ticket_id: 't-202',
    chat_id: 'c-202',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L2',
    client: {
      company_name: 'ООО «СтройКомплект»',
      inn: '7705412398',
      phone: '+7 (495) 654-32-10',
      full_name: 'Морозов Дмитрий Константинович',
      email: 'morozov@stroykomplekt.ru',
    },
    copilot_summary: {
      summary: 'Ошибка валидации схемы XML универсального передаточного документа (УПД) по приказу ФНС 820.',
      suggested_line_code: 'L2',
      suggested_response: 'Здравствуйте, Дмитрий Константинович! В вашем XML-файле УПД отсутствует обязательный реквизит ИГК (Идентификатор государственного контракта). Добавьте тег <СвГосКонтр ИдентГосКонтр="..."/> в структуру документа.',
      recommended_chunk_ids: ['chunk-upd-order820-spec'],
    },
    messages: [
      {
        id: 'm-202-1',
        content: 'Не могу прикрепить УПД к исполненному контракту №9923/26. Выдает "Ошибка формата XML файла УПД по приказу 820".',
        type: 'user',
        timestamp: '14:40',
        actions: [],
      },
    ],
  },
  't-203': {
    ticket_id: 't-203',
    chat_id: 'c-203',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L2',
    client: {
      company_name: 'АО «МедСнабжение»',
      inn: '7708912345',
      phone: '+7 (495) 234-56-78',
      full_name: 'Васильева Ольга Павловна',
      email: 'vasilyeva@medsnab.ru',
    },
    copilot_summary: {
      summary: 'Зависание диалогового окна cadesplugin на шаге вызова функции SignHash в браузере Chromium.',
      suggested_line_code: 'L2',
      suggested_response: 'Здравствуйте, Ольга Павловна! Данный сбой вызван конфликтом версий расширения. Рекомендуем выполнить сброс кэша браузера и обновить CAdES Browser Plug-in до актуальной версии 2.0.15000.',
      recommended_chunk_ids: ['chunk-cadesplugin-hang'],
    },
    messages: [
      {
        id: 'm-203-1',
        content: 'При нажатии "Подписать протокол" окно плагина ЭЦП зависает на этапе "Инициализация криптопровайдера...". Как решить?',
        type: 'user',
        timestamp: '14:20',
        actions: [],
      },
    ],
  },
};

const DEFAULT_WORKSPACES_L3: Record<string, OperatorTicketWorkspace> = {
  't-301': {
    ticket_id: 't-301',
    chat_id: 'c-301',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L3',
    client: {
      company_name: 'ООО «ИнфоТех»',
      inn: '7709841235',
      phone: '+7 (495) 789-01-23',
      full_name: 'Зайцев Евгений Михайлович',
      email: 'zaytsev@infotech.ru',
    },
    copilot_summary: {
      summary: 'Сбой интеграционного шлюза ЕАИСТ / ЭДО Диадок: задержка отправки пакетов УПД, таймауты SOAP-запросов.',
      suggested_line_code: 'L3',
      suggested_response: 'Здравствуйте, Евгений Михайлович! Инцидент INC-8401 передан дежурному инженеру DevOps. Ведется перезапуск интеграционного шлюза и дренаж очереди пакетов. Восстановление ожидается в течение 20 минут.',
      recommended_chunk_ids: ['chunk-infra-gateway-diadoc'],
      similar_resolved_tickets: [
        {
          ticket_id: 't-012',
          support_line: 'L3',
          user_query: 'Сбой шлюза ЭДО Диадок',
          solution_text: 'Перезапуск подов шлюза и повторный запуск консюмеров RabbitMQ.',
          similarity_score: 0.98,
        },
      ],
    },
    messages: [
      {
        id: 'm-301-1',
        content: 'Критическая авария: отказ интеграционного шлюза ЕАИСТ / ЭДО Диадок, зависли 45 пакетов УПД! Просьба срочно эскалировать администраторам.',
        type: 'user',
        timestamp: '15:25',
        actions: [],
      },
    ],
  },
  't-302': {
    ticket_id: 't-302',
    chat_id: 'c-302',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L3',
    client: {
      company_name: 'ООО «ДатаГрупп»',
      inn: '7707654321',
      phone: '+7 (495) 456-78-90',
      full_name: 'Белов Андрей Сергеевич',
      email: 'belov@datagroup.ru',
    },
    copilot_summary: {
      summary: 'Зависание очереди асинхронного парсера YML-каталога в Redis: превышение лимита памяти воркеров Celery.',
      suggested_line_code: 'L3',
      suggested_response: 'Здравствуйте, Андрей Сергеевич! Диагностировали переполнение очереди воркеров парсинга. Добавили 4 дополнительных пода-обработчика, очередь начала рассасываться.',
      recommended_chunk_ids: ['chunk-infra-redis-parser'],
    },
    messages: [
      {
        id: 'm-302-1',
        content: 'Очередь асинхронного парсера YML зависла на 0% в Redis, таймаут фоновых воркеров при обработке прайса на 15 000 позиций.',
        type: 'user',
        timestamp: '15:00',
        actions: [],
      },
    ],
  },
  't-303': {
    ticket_id: 't-303',
    chat_id: 'c-303',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L3',
    client: {
      company_name: 'ООО «ИТ-Решения»',
      inn: '7703344556',
      phone: '+7 (495) 321-65-49',
      full_name: 'Романова Ксения Игоревна',
      email: 'romanova@it-solutions.ru',
    },
    copilot_summary: {
      summary: 'HTTP 502 Bad Gateway при массовой генерации PDF протоколов котировочных сессий в часы пиковой нагрузки.',
      suggested_line_code: 'L3',
      suggested_response: 'Здравствуйте, Ксения Игоревна! Увеличен пул коннектов PostgreSQL и скорректирован таймаут nginx upstream для генератора PDF. Ошибка 502 устранена.',
      recommended_chunk_ids: ['chunk-infra-pg-pool'],
    },
    messages: [
      {
        id: 'm-303-1',
        content: 'Ошибка 502 Bad Gateway при массовой выгрузке закрывающих протоколов котировочных сессий. База не отвечает.',
        type: 'user',
        timestamp: '14:35',
        actions: [],
      },
    ],
  },
};

function getLocalStoredTickets(): OperatorSidebarTicket[] {
  const line = getOperatorLineCode();
  try {
    const raw = localStorage.getItem(`${STORAGE_TICKETS_KEY}_${line}`);
    if (raw) return JSON.parse(raw);
  } catch {}
  if (line === 'L2') return DEFAULT_TICKETS_L2;
  if (line === 'L3') return DEFAULT_TICKETS_L3;
  return DEFAULT_TICKETS_L1;
}

function saveLocalStoredTickets(tickets: OperatorSidebarTicket[]) {
  const line = getOperatorLineCode();
  try {
    localStorage.setItem(`${STORAGE_TICKETS_KEY}_${line}`, JSON.stringify(tickets));
  } catch {}
}

function getLocalWorkspaces(): Record<string, OperatorTicketWorkspace> {
  const line = getOperatorLineCode();
  try {
    const raw = localStorage.getItem(`${STORAGE_WORKSPACES_KEY}_${line}`);
    if (raw) return JSON.parse(raw);
  } catch {}
  if (line === 'L2') return DEFAULT_WORKSPACES_L2;
  if (line === 'L3') return DEFAULT_WORKSPACES_L3;
  return DEFAULT_WORKSPACES_L1;
}

function saveLocalWorkspaces(workspaces: Record<string, OperatorTicketWorkspace>) {
  const line = getOperatorLineCode();
  try {
    localStorage.setItem(`${STORAGE_WORKSPACES_KEY}_${line}`, JSON.stringify(workspaces));
  } catch {}
}

export async function getOperatorShift(): Promise<OperatorProfile> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const res = await fetch('/api/v1/operators/me/shift', {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {}
  }

  return getOperatorProfileForUser();
}

export async function updateOperatorShift(shift_status: ShiftStatus): Promise<OperatorProfile> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const res = await fetch('/api/v1/operators/me/shift', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
        body: JSON.stringify({ shift_status }),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {}
  }

  const line = getOperatorLineCode();
  localStorage.setItem(`${STORAGE_SHIFT_KEY}_${line}`, shift_status);
  const baseProfile = getOperatorProfileForUser();
  return {
    ...baseProfile,
    shift_status,
  };
}

export async function getOperatorTickets(): Promise<OperatorSidebarTicket[]> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const res = await fetch('/api/v1/operators/tickets', {
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {}
  }

  return getLocalStoredTickets();
}

function mapOperatorMessage(m: any): Message {
  const senderType: 'client' | 'bot' | 'operator' | 'system' =
    m.sender_type ||
    (m.type === 'user' ? 'client' : m.id?.startsWith('op-') ? 'operator' : m.id?.startsWith('bot-') ? 'bot' : 'operator');

  let type: 'user' | 'assistant' | 'system' = 'assistant';
  if (senderType === 'client') {
    type = 'user';
  } else if (senderType === 'system') {
    type = 'system';
  } else {
    type = 'assistant';
  }

  const timeStr = m.created_at
    ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : m.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return {
    id: String(m.id),
    ticket_id: m.ticket_id ? String(m.ticket_id) : undefined,
    content: m.text || m.content || '',
    type,
    sender_type: senderType,
    timestamp: timeStr,
    actions: ['copy'],
    citations: m.sources?.map((s: any, idx: number) => ({
      id: s.chunk_id || `c-${idx}`,
      title: s.doc_id || 'Регламент Портала',
      sectionPath: s.doc_id,
      excerpt: s.quote_text,
    })),
  };
}

export async function openTicketWorkspace(ticketId: string): Promise<OperatorTicketWorkspace> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const res = await fetch(`/api/v1/operators/tickets/${ticketId}/open`, {
        method: 'POST',
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });
      if (res.ok) {
        const data = await res.json();
        return {
          ...data,
          messages: (data.messages || []).map(mapOperatorMessage),
        };
      }
    } catch {}
  }

  const workspaces = getLocalWorkspaces();
  const ws = workspaces[ticketId];
  if (ws) {
    // mark as in_progress
    ws.status = 'in_progress';
    saveLocalWorkspaces(workspaces);

    const tickets = getLocalStoredTickets().map((t) =>
      t.ticket_id === ticketId ? { ...t, status: 'in_progress' as const, unread_messages_count: 0 } : t
    );
    saveLocalStoredTickets(tickets);

    return ws;
  }

  throw new Error('Ticket workspace not found');
}

export async function sendOperatorMessage(ticketId: string, text: string): Promise<OperatorTicketWorkspace> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      const res = await fetch(`/api/v1/operators/tickets/${ticketId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
        body: JSON.stringify({ text }),
      });
      if (res.ok) {
        // Refresh workspace
        return await openTicketWorkspace(ticketId);
      }
    } catch {}
  }

  const workspaces = getLocalWorkspaces();
  const ws = workspaces[ticketId];
  if (ws) {
    const operatorMsg = {
      id: `op-msg-${Date.now()}`,
      content: text,
      type: 'assistant' as const,
      sender_type: 'operator' as const,
      sender_name: getOperatorProfileForUser().full_name,
      sender_role: 'operator',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      actions: ['copy' as const],
    };
    ws.messages.push(operatorMsg);
    saveLocalWorkspaces(workspaces);

    // Sync to mock client state if exists
    try {
      const rawMockChat = localStorage.getItem('portal_mock_chat_state');
      if (rawMockChat) {
        const mockChat = JSON.parse(rawMockChat);
        mockChat.messages.push({
          id: operatorMsg.id,
          ticket_id: ticketId,
          sender_type: 'operator',
          sender_name: 'Смирнова Анна Сергеевна',
          sender_role: 'operator',
          text: text,
          created_at: new Date().toISOString(),
        });
        localStorage.setItem('portal_mock_chat_state', JSON.stringify(mockChat));
      }
    } catch {}

    // Update last message preview
    const tickets = getLocalStoredTickets().map((t) =>
      t.ticket_id === ticketId
        ? {
            ...t,
            last_message_preview: `Оператор: ${text.slice(0, 50)}${text.length > 50 ? '...' : ''}`,
          }
        : t
    );
    saveLocalStoredTickets(tickets);

    return ws;
  }

  throw new Error('Ticket not found');
}

export async function transferTicket(
  ticketId: string,
  targetLineCode: string,
  comment?: string
): Promise<void> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      await fetch(`/api/v1/operators/tickets/${ticketId}/transfer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
        body: JSON.stringify({
          target_line_code: targetLineCode,
          transfer_comment: comment,
        }),
      });
    } catch {}
  }

  // Remove from operator's assigned tickets
  const tickets = getLocalStoredTickets().filter((t) => t.ticket_id !== ticketId);
  saveLocalStoredTickets(tickets);

  const workspaces = getLocalWorkspaces();
  if (workspaces[ticketId]) {
    workspaces[ticketId].line_code = targetLineCode;
    workspaces[ticketId].transfer_comment = comment;
    workspaces[ticketId].messages.push({
      id: `sys-${Date.now()}`,
      content: `Тикет переведен на линию ${targetLineCode}. Комментарий: ${comment || 'Без комментария'}`,
      type: 'system',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      actions: [],
    });
    saveLocalWorkspaces(workspaces);
  }
}

export async function resolveOperatorTicket(ticketId: string): Promise<void> {
  if (!isStandaloneMode()) {
    try {
      const tokens = getStoredTokens();
      await fetch(`/api/v1/operators/tickets/${ticketId}/resolve`, {
        method: 'POST',
        headers: {
          Authorization: tokens?.access_token ? `Bearer ${tokens.access_token}` : '',
        },
      });
    } catch {}
  }

  // Remove from active sidebar
  const tickets = getLocalStoredTickets().filter((t) => t.ticket_id !== ticketId);
  saveLocalStoredTickets(tickets);
}

export { mapOperatorMessage };

export function subscribeOperatorEvents(
  onEvent?: (event: string, data: any) => void
): () => void {
  if (isStandaloneMode()) {
    return () => {};
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    return () => {};
  }

  const controller = new AbortController();
  const url = `/api/v1/operators/events?token=${tokens.access_token}`;

  fetch(url, {
    signal: controller.signal,
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${tokens.access_token}`,
    },
  })
    .then(async (res) => {
      if (!res.ok || !res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const lines = part.split('\n');
          let currentEvent = 'message';
          let currentData = '';

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              currentData = line.replace('data:', '').trim();
            }
          }

          if (currentData) {
            try {
              const parsed = JSON.parse(currentData);
              onEvent?.(currentEvent, parsed);
            } catch {
              onEvent?.(currentEvent, currentData);
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        console.warn('Operator SSE error:', err);
      }
    });

  return () => {
    controller.abort();
  };
}
