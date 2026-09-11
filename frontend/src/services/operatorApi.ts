import {
  OperatorProfile,
  OperatorSidebarTicket,
  OperatorTicketWorkspace,
  ShiftStatus,
} from '../types/operator';
import { Message } from '../types/chat';
import { getStoredTokens } from './auth';
import { isStandaloneMode } from '../config/mode';

const STORAGE_SHIFT_KEY = 'portal_operator_shift';
const STORAGE_TICKETS_KEY = 'portal_operator_tickets';
const STORAGE_WORKSPACES_KEY = 'portal_operator_workspaces';

const DEFAULT_PROFILE: OperatorProfile = {
  user_id: 'op-001',
  full_name: 'Смирнова Анна Сергеевна',
  line_id: 1,
  line_code: 'L1',
  shift_status: 'active',
  max_slots: 5,
  active_slots_count: 3,
};

const DEFAULT_TICKETS: OperatorSidebarTicket[] = [
  {
    ticket_id: 't-101',
    chat_id: 'c-101',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L1',
    client_name: 'Кузнецов В.А.',
    company_name: 'ООО «ПромСервис Поставка»',
    last_message_preview: 'Срочно! Истекает срок подписания контракта КС-9482, ошибка КриптоПро.',
    unread_messages_count: 2,
    created_at: '10 мин. назад',
    assigned_at: 'Только что',
  },
  {
    ticket_id: 't-102',
    chat_id: 'c-102',
    priority: 'P1',
    status: 'in_progress',
    line_code: 'L1',
    client_name: 'Иванов И.И.',
    company_name: 'ООО «ТехноСнаб»',
    last_message_preview: 'Не подгружается машиночитаемая доверенность (МЧД) из реестра ФНС.',
    unread_messages_count: 1,
    created_at: '25 мин. назад',
    assigned_at: '15 мин. назад',
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

const DEFAULT_WORKSPACES: Record<string, OperatorTicketWorkspace> = {
  't-101': {
    ticket_id: 't-101',
    chat_id: 'c-101',
    priority: 'P0',
    status: 'assigned',
    line_code: 'L1',
    client: {
      company_name: 'ООО «ПромСервис Поставка»',
      inn: '7701984512',
      kpp: '770101001',
      phone: '+7 (495) 780-12-34',
      full_name: 'Кузнецов Валерий Алексеевич',
      email: 'kuznetsov@promservice.ru',
    },
    copilot_summary: {
      summary: 'Критический сбой при подписании оферты котировочной сессии КС-9482. Ошибка плагина КриптоПро 0x80090014.',
      suggested_line_code: 'L2',
      suggested_response: 'Уважаемый Валерий Алексеевич! Для устранения ошибки КриптоПро 0x80090014 выполните очистку SSL-кэша браузера и переустановите КриптоПро ЭЦП Browser Plug-in версии 2.0.15000. Если ошибка сохранится, я переведу вас на инженера 2-й линии технической поддержки.',
      recommended_chunk_ids: ['chunk-crypto-p4', 'chunk-signing-reg-v3'],
      similar_resolved_tickets: [
        {
          ticket_id: 't-084',
          support_line: 'L2',
          user_query: 'Ошибка валидации сертификата при подписании контракта',
          solution_text: 'Выполнена переустановка корневых сертификатов Минцифры и очистка кэша КриптоПро.',
          similarity_score: 0.94,
        },
      ],
    },
    messages: [
      {
        id: 'm-1',
        content: 'Здравствуйте! Не могу подписать контракт по котировочной сессии КС-9482. До окончания регламентного срока осталось 40 минут! Выдает ошибку плагина.',
        type: 'user',
        timestamp: '15:10',
        actions: [],
      },
      {
        id: 'm-2',
        content: 'Для подписания документов требуется квалифицированная электронная подпись (УКЭП) и настроенный КриптоПро ЭЦП Browser plug-in.',
        type: 'assistant',
        timestamp: '15:10',
        actions: [],
      },
      {
        id: 'm-3',
        content: 'Бот не помог, соедините срочно с оператором!',
        type: 'user',
        timestamp: '15:12',
        actions: [],
      },
    ],
  },
  't-102': {
    ticket_id: 't-102',
    chat_id: 'c-102',
    priority: 'P1',
    status: 'in_progress',
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
        id: 'm-10',
        content: 'Добрый день. Пытаюсь загрузить МЧД из реестра ФНС, пишет «Доверенность не найдена или не активна». Но в ФНС статус «Зарегистрирована».',
        type: 'user',
        timestamp: '14:50',
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
        id: 'm-20',
        content: 'Здравствуйте, подскажите, в какой срок поставщик имеет право направить протокол разногласий?',
        type: 'user',
        timestamp: '14:15',
        actions: [],
      },
    ],
  },
};

function getLocalStoredTickets(): OperatorSidebarTicket[] {
  try {
    const raw = localStorage.getItem(STORAGE_TICKETS_KEY);
    return raw ? JSON.parse(raw) : DEFAULT_TICKETS;
  } catch {
    return DEFAULT_TICKETS;
  }
}

function saveLocalStoredTickets(tickets: OperatorSidebarTicket[]) {
  try {
    localStorage.setItem(STORAGE_TICKETS_KEY, JSON.stringify(tickets));
  } catch {}
}

function getLocalWorkspaces(): Record<string, OperatorTicketWorkspace> {
  try {
    const raw = localStorage.getItem(STORAGE_WORKSPACES_KEY);
    return raw ? JSON.parse(raw) : DEFAULT_WORKSPACES;
  } catch {
    return DEFAULT_WORKSPACES;
  }
}

function saveLocalWorkspaces(workspaces: Record<string, OperatorTicketWorkspace>) {
  try {
    localStorage.setItem(STORAGE_WORKSPACES_KEY, JSON.stringify(workspaces));
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

  const rawShift = localStorage.getItem(STORAGE_SHIFT_KEY) as ShiftStatus | null;
  return {
    ...DEFAULT_PROFILE,
    shift_status: rawShift || 'active',
  };
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

  localStorage.setItem(STORAGE_SHIFT_KEY, shift_status);
  return {
    ...DEFAULT_PROFILE,
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
    ws.messages.push({
      id: `op-msg-${Date.now()}`,
      content: text,
      type: 'assistant',
      sender_type: 'operator',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      actions: ['copy'],
    });
    saveLocalWorkspaces(workspaces);

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
